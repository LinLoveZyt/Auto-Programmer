# auto_programmer_core/project_builder.py
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import shutil
import json

logger = logging.getLogger(__name__)

class ProjectBuilder:
    """
    根据结构化数据（通常是LLM生成的JSON）构建项目的文件和目录结构。
    新增了应用具体修改指令的能力。
    """

    def _sanitize_requirements_content(self, file_path_str: str, content: str) -> str:
        """
        修正 LLM 可能为 requirements.txt 生成的错误内容。
        如果内容是一个包含 'content' 键的JSON字符串, 则提取其内部的真实内容。
        这是一个针对观察到的特定LLM错误的健壮性修复。
        """
        # 这个修正逻辑只针对 requirements.txt 文件
        if Path(file_path_str).name != 'requirements.txt':
            return content

        try:
            # 尝试将整个内容字符串解析为JSON
            data = json.loads(content)
            # 如果解析成功，并且结果是一个包含 'content' 键的字典
            if isinstance(data, dict) and 'content' in data:
                # 提取出真正的、应有的内容
                new_content = data['content']
                if isinstance(new_content, str):
                    logger.warning(
                        f"检测到并修正了 requirements.txt 的内容。原始: '{content}', 修正后: '{new_content}'"
                    )
                    return new_content
        except (json.JSONDecodeError, TypeError):
            # 如果内容不是一个有效的JSON字符串, 说明它可能是正确的格式 (例如 "pytest\npsutil")
            # 直接返回原始内容
            return content
        
        # 如果能解析为JSON但格式不符合错误模式, 也返回原始内容
        return content

    def build_project_structure(self,
                                base_path: Path,
                                files: List[Dict[str, str]]) -> bool:
        """
        在给定的基础路径下，创建所有文件和必要的子目录。
        这是一个基于“完全替换”逻辑的构建方法，用于项目的初始步骤。
        """
        logger.info(f"开始在 '{base_path}' 目录下构建项目结构...")

        try:
            # 确保基础路径是一个干净的目录
            if base_path.exists():
                shutil.rmtree(base_path)
            base_path.mkdir(parents=True)

            if not files:
                logger.warning("文件列表为空，未创建任何文件。")
                return True

            for file_info in files:
                file_path_str = file_info.get("path")
                content = file_info.get("content", "")

                if not file_path_str:
                    logger.warning(f"文件信息缺少 'path' 键，已跳过: {file_info}")
                    continue

                # --- 修改开始: 在写入前净化内容 ---
                sanitized_content = self._sanitize_requirements_content(file_path_str, content)
                # --- 修改结束 ---

                full_path = base_path / Path(file_path_str)
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(sanitized_content, encoding='utf-8') # 使用净化后的内容
                logger.debug(f"成功创建文件: {full_path}")

            logger.info(f"项目结构在 '{base_path}' 中成功构建。")
            return True
        except Exception as e:
            logger.error(f"在 '{base_path}' 构建项目结构时发生错误: {e}", exc_info=True)
            return False

    def apply_modifications(self, base_path: Path, target_path: Path, instructions: List[Dict]) -> bool:
        """
        在一个基础代码版本上，应用一系列修改指令，并生成到目标路径。
        这是新增的、基于“精确修改”逻辑的构建方法。
        """
        logger.info(f"正在从 '{base_path}' 应用修改到 '{target_path}'...")
        try:
            # 1. 准备目标目录：如果存在则清空，然后从基础路径完整复制
            if target_path.exists():
                shutil.rmtree(target_path)
            
            if base_path.is_dir():
                shutil.copytree(base_path, target_path)
            else:
                # 如果基础路径由于某种原因不存在，则创建一个空的目标目录
                target_path.mkdir(parents=True, exist_ok=True)

            # 2. 遍历并执行每一条修改指令
            for instruction in instructions:
                mod_type = instruction.get("type")
                rel_path_str = instruction.get("path")
                if not rel_path_str:
                    logger.warning(f"指令缺少 'path'，已跳过: {instruction}")
                    continue

                file_path = target_path / rel_path_str
                content = instruction.get("content", "")

                # --- 修改开始: 在写入前净化内容 ---
                sanitized_content = self._sanitize_requirements_content(rel_path_str, content)
                # --- 修改结束 ---

                if mod_type == "replace_file" or mod_type == "new_file":
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(sanitized_content, encoding='utf-8') # 使用净化后的内容
                    if mod_type == "replace_file":
                        logger.info(f"[指令] 文件已替换: {file_path}")
                    else:
                        logger.info(f"[指令] 新文件已创建: {file_path}")
                elif mod_type == "line_diff":
                    self._apply_line_diffs(file_path, instruction.get("diffs", []))
                elif mod_type == "delete_file":
                    if file_path.exists() and file_path.is_file():
                        file_path.unlink()
                        logger.info(f"[指令] 文件已删除: {file_path}")
                    else:
                        logger.warning(f"[指令] 尝试删除不存在的文件，已忽略: {file_path}")
                else:
                    logger.warning(f"[指令] 未知的修改类型 '{mod_type}'，已忽略。")


            logger.info("所有修改指令应用成功。")
            return True
        except Exception as e:
            logger.error(f"应用修改指令时出错: {e}", exc_info=True)
            return False

    def _apply_line_diffs(self, file_path: Path, diffs: List[Dict]):
        """辅助方法，用于处理行级修改。"""
        if not file_path.exists():
            # 如果文件不存在，可能是LLM意图创建一个新文件
            logger.warning(f"尝试对一个不存在的文件 '{file_path}' 进行行级修改。将当作新文件创建。")
            all_new_content = [diff.get("new_content", "") for diff in diffs]
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("\n".join(all_new_content), encoding='utf-8')
            logger.info(f"[指令] 行级修改生成了新文件: {file_path}")
            return

        lines = file_path.read_text(encoding='utf-8').splitlines()

        # 为了应对多次修改，必须倒序处理，这样行号不会因为前面的修改而错位
        for diff in sorted(diffs, key=lambda x: x.get('start_line', 0), reverse=True):
            start_line = diff.get("start_line", 1) - 1  # 转换为0-based索引
            end_line = diff.get("end_line", start_line + 1)
            new_content_lines = diff.get("new_content", "").splitlines()

            # 确保索引在有效范围内
            if start_line < 0 or end_line > len(lines) or start_line >= end_line:
                 logger.warning(f"行级修改的行号范围无效，已跳过: start={start_line+1}, end={end_line}. 文件: {file_path}")
                 continue

            lines[start_line:end_line] = new_content_lines

        file_path.write_text("\n".join(lines), encoding='utf-8')
        logger.info(f"[指令] 行级修改已应用于: {file_path}")