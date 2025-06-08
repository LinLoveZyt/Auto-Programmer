# auto_programmer_core/prompt_manager.py
import os
import logging
import re
from typing import Set

logger = logging.getLogger(__name__)

class PromptManager:
    """
    Prompt管理器，负责加载、格式化和填充Prompt模板。
    支持通过 {{include 'template_key'}} 语法来嵌套模板。
    """
    def __init__(self, template_dir: str):
        self.template_dir = template_dir
        if not os.path.isdir(template_dir):
            logger.error(f"Prompt模板目录 '{template_dir}' 不存在或不是一个目录。")
            raise FileNotFoundError(f"Prompt模板目录 '{template_dir}' 不存在。")
        logger.info(f"PromptManager 初始化完成，模板目录: {template_dir}")

    def _load_template_content(self, template_key: str) -> str:
        template_filename = f"{template_key}.txt"
        template_path = os.path.join(self.template_dir, template_filename)
        if not os.path.exists(template_path):
            logger.error(f"模板文件 '{template_path}' 未找到。")
            raise FileNotFoundError(f"模板文件 '{template_path}' 未找到。")
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()

    def _resolve_includes_in_content(self, content: str, seen_keys: Set[str]) -> str:
        include_pattern = re.compile(r"\{\{include\s+'([^']+)'\}\}")
        def replacer(match):
            included_key = match.group(1)
            if included_key in seen_keys:
                raise RecursionError(f"检测到循环模板引用: '{included_key}' 已在加载路径中。")
            included_content = self._load_template_content(included_key)
            new_seen_keys = seen_keys.copy()
            new_seen_keys.add(included_key)
            return self._resolve_includes_in_content(included_content, new_seen_keys)
        return include_pattern.sub(replacer, content)

    def load_and_format_prompt(self, template_key: str, **kwargs) -> str:
        """
        加载指定的Prompt模板文件，解析所有 include 指令，并使用提供的参数格式化最终内容。
        """
        logger.debug(f"开始加载和格式化Prompt '{template_key}'...")
        try:
            main_content = self._load_template_content(template_key)
            resolved_template = self._resolve_includes_in_content(main_content, seen_keys={template_key})
            logger.debug(f"模板 '{template_key}' 的所有 include 指令已解析完成。")

            # --- 新增的调试和错误处理逻辑 ---
            try:
                formatted_prompt = resolved_template.format(**kwargs)
                logger.debug(f"成功格式化Prompt '{template_key}'")
                return formatted_prompt
            except KeyError as e:
                logger.error(f"格式化模板 '{template_key}' 时发生 KeyError: {e}")
                logger.error("这是一个严重错误，通常意味着模板中的占位符与代码提供的数据不匹配。")
                logger.error(f"--- 导致错误的模板内容 (前500字符) ---\n{resolved_template[:500]}\n---")
                logger.error(f"--- 代码提供的所有可用关键字 ---\n{list(kwargs.keys())}\n---")
                # 重新抛出异常，让上层代码知道发生了错误
                raise
            # --- 错误处理逻辑结束 ---
            
        except (FileNotFoundError, RecursionError) as e:
            logger.error(f"处理Prompt模板 '{template_key}' 时发生错误: {e}")
            raise
        except Exception as e:
            logger.error(f"加载或格式化Prompt模板 '{template_key}' 时发生未知错误: {e}")
            raise