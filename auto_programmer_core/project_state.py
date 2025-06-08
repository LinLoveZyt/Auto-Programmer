# auto_programmer_core/project_state.py
import logging
import json
import shutil
from pathlib import Path
from datetime import datetime
import uuid
from typing import Dict, Optional, Any

from .config_manager import ConfigManager

logger = logging.getLogger(__name__)

class ProjectState:
    """
    管理项目会话的状态，包括工作区创建和数据持久化。
    """
    RAW_INPUT_FILENAME = "user_raw_input.txt"
    PROJECT_DEFINITION_FILENAME = "project_definition.json"
    TASK_STEPS_FILENAME = "task_steps.json"
    
    # --- 新增 ---
    ARCHITECTURE_NOTES_FILENAME = "architecture_notes.md" 

    GENERATED_CODE_ROOT_DIR = "generated_code"
    STEP_ATTEMPTS_DIR_TEMPLATE = "step_{step_number}_attempts"
    ATTEMPT_DIR_TEMPLATE = "attempt_{attempt_number}"
    STEP_CODE_OUTPUT_FILENAME = "code_generation_output.json"

    EXECUTION_STDOUT_FILENAME = "execution_stdout.txt"
    EXECUTION_STDERR_FILENAME = "execution_stderr.txt"
    EXECUTION_RESULT_FILENAME = "execution_result.json"
    INSTALL_LOG_FILENAME = "install_log.txt"

    ERROR_SUMMARY_FILENAME = "error_summary.txt"
    USER_FEEDBACK_FILENAME = "user_feedback.txt"
    INSPECTOR_FEEDBACK_FILENAME = "inspector_feedback.txt" 
    
    SUCCESSFUL_STEPS_DIR = "successful_steps"
    LATEST_SUCCESSFUL_CODE_DIR = "latest_successful_code"
    STEP_SUMMARY_FILENAME = "step_summary.json" 
    ARCHIVE_MANIFEST_FILENAME = "archive_manifest.txt" 

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.project_root_dir = Path(self.config_manager.get_project_config().get("root_directory", "./workspace"))
        self.current_workspace: Optional[Path] = None
        self.project_name: Optional[str] = None
        logger.info(f"ProjectState 初始化，项目根目录: {self.project_root_dir}")

    def initialize_workspace(self) -> Path:
        """
        在配置的 root_directory 下，创建一个唯一的项目工作区目录，并存储其名称。
        同时创建用于存放成功步骤代码和最新代码的子目录。
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        self.project_name = f"proj_{timestamp}_{unique_id}"
        
        self.current_workspace = self.project_root_dir / self.project_name
        try:
            self.current_workspace.mkdir(parents=True, exist_ok=True)
            (self.current_workspace / self.SUCCESSFUL_STEPS_DIR).mkdir(exist_ok=True)
            (self.current_workspace / self.LATEST_SUCCESSFUL_CODE_DIR).mkdir(exist_ok=True)
            
            # --- 新增：创建初始的架构知识库文件 ---
            (self.current_workspace / self.ARCHITECTURE_NOTES_FILENAME).touch()

            logger.info(f"成功创建项目工作区: {self.current_workspace} (项目ID: {self.project_name})")
            return self.current_workspace
        except OSError as e:
            logger.error(f"创建项目工作区 {self.current_workspace} 失败: {e}")
            raise

    # --- 新增：管理架构知识库的方法 ---
    def save_architecture_notes(self, new_notes: str):
        """将新的架构笔记追加到知识库文件中。"""
        workspace_path = self._get_workspace_path()
        file_path = workspace_path / self.ARCHITECTURE_NOTES_FILENAME
        try:
            with file_path.open('a', encoding='utf-8') as f:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"\n\n---\n")
                f.write(f"笔记时间: {timestamp}\n")
                f.write(f"---\n")
                f.write(new_notes)
            logger.info(f"新的架构笔记已追加到: {file_path}")
        except OSError as e:
            logger.error(f"追加架构笔记至 {file_path} 失败: {e}")

    def load_architecture_notes(self) -> str:
        """加载完整的架构知识库内容。"""
        workspace_path = self._get_workspace_path()
        file_path = workspace_path / self.ARCHITECTURE_NOTES_FILENAME
        if not file_path.exists():
            return "尚无架构笔记。"
        try:
            return file_path.read_text(encoding='utf-8')
        except OSError as e:
            logger.error(f"读取架构笔记文件 {file_path} 失败: {e}")
            return f"读取架构笔记文件失败: {e}"
    # --- 新增结束 ---

    def archive_project(self):
        """
        执行项目归档操作。当前实现为生成一个清单文件。
        未来可扩展为压缩工作区等。
        """
        workspace_path = self._get_workspace_path()
        manifest_path = workspace_path / self.ARCHIVE_MANIFEST_FILENAME
        
        logger.info(f"开始对项目工作区 '{workspace_path}' 进行归档...")
        
        try:
            with manifest_path.open('w', encoding='utf-8') as f:
                f.write(f"项目归档清单\n")
                f.write(f"项目名称: {self.project_name}\n")
                f.write(f"归档时间: {datetime.now().isoformat()}\n")
                f.write(f"工作区路径: {workspace_path.resolve()}\n")
                f.write("\n--- 主要产物 ---\n")
                
                key_artifacts = [
                    self.RAW_INPUT_FILENAME,
                    self.PROJECT_DEFINITION_FILENAME,
                    self.TASK_STEPS_FILENAME,
                    self.ARCHITECTURE_NOTES_FILENAME, # 归档时包含知识库
                    self.GENERATED_CODE_ROOT_DIR,
                    self.SUCCESSFUL_STEPS_DIR,
                    self.LATEST_SUCCESSFUL_CODE_DIR,
                    self.config_manager.get_logging_config().get("log_file")
                ]
                
                for artifact in key_artifacts:
                    if artifact:
                        artifact_path = workspace_path / artifact
                        if artifact_path.exists():
                            f.write(f"- {artifact} ({'目录' if artifact_path.is_dir() else '文件'})\n")
            
            logger.info(f"项目归档清单已生成: {manifest_path}")
            print(f"✅ 项目已归档，详情请见: {manifest_path}")
        except Exception as e:
            logger.error(f"生成项目归档清单时发生错误: {e}", exc_info=True)
            print(f"❌ 项目归档操作失败。")
            
    def _get_workspace_path(self) -> Path:
        if not self.current_workspace:
            logger.error("项目工作区尚未初始化。请先调用 initialize_workspace()")
            raise ValueError("Workspace not initialized.")
        return self.current_workspace

    def _read_directory_to_json(self, dir_path: Path) -> Dict[str, Any]:
        """
        辅助函数：递归读取一个目录下的所有文件，并将其转换为LLM期望的JSON格式。
        """
        files_list = []
        if not dir_path.is_dir():
            return {"files": []}

        for item in sorted(list(dir_path.glob('**/*'))):
            if item.is_file():
                try:
                    # 排除更多的元数据文件
                    if item.name in [
                        self.STEP_SUMMARY_FILENAME, 
                        self.INSPECTOR_FEEDBACK_FILENAME, 
                        self.USER_FEEDBACK_FILENAME,
                        self.STEP_CODE_OUTPUT_FILENAME,
                        self.EXECUTION_STDOUT_FILENAME,
                        self.EXECUTION_STDERR_FILENAME,
                        self.EXECUTION_RESULT_FILENAME,
                        self.INSTALL_LOG_FILENAME,
                        self.ERROR_SUMMARY_FILENAME
                    ]:
                        continue
                    relative_path = item.relative_to(dir_path)
                    content = item.read_text(encoding='utf-8')
                    files_list.append({
                        "path": str(relative_path).replace('\\', '/'),
                        "content": content
                    })
                except Exception as e:
                    logger.warning(f"读取文件 {item} 时出错，已跳过: {e}")
        return {"files": files_list}

    def mark_step_as_successful(self, step_number: int, successful_attempt_path: Path):
        """
        将一个步骤标记为成功，将其代码快照保存，并更新“最新成功代码”目录。
        """
        workspace_path = self._get_workspace_path()
        successful_step_path = workspace_path / self.SUCCESSFUL_STEPS_DIR / f"step_{step_number}"
        latest_code_path = workspace_path / self.LATEST_SUCCESSFUL_CODE_DIR

        try:
            # 1. 保存当前步骤的快照
            if successful_step_path.exists():
                shutil.rmtree(successful_step_path)
            shutil.copytree(successful_attempt_path, successful_step_path)
            logger.info(f"已将步骤 {step_number} 的成功代码快照从 {successful_attempt_path} 保存到 {successful_step_path}")

            # 2. 更新最新成功代码目录
            if latest_code_path.exists():
                shutil.rmtree(latest_code_path)
            shutil.copytree(successful_attempt_path, latest_code_path)
            logger.info(f"已将最新的成功代码更新为步骤 {step_number} 的产出，路径: {latest_code_path}")

        except Exception as e:
            logger.error(f"标记步骤 {step_number} 为成功时，复制文件出错: {e}", exc_info=True)
            raise

    def save_step_summary(self, step_number: int, summary_json: Dict):
        """为成功的步骤保存AI生成的总结。"""
        workspace_path = self._get_workspace_path()
        successful_step_path = workspace_path / self.SUCCESSFUL_STEPS_DIR / f"step_{step_number}"
        file_path = successful_step_path / self.STEP_SUMMARY_FILENAME
        
        successful_step_path.mkdir(exist_ok=True)

        try:
            with file_path.open('w', encoding='utf-8') as f:
                json.dump(summary_json, f, indent=4, ensure_ascii=False)
            logger.info(f"步骤 {step_number} 的代码总结已保存至: {file_path}")
        except (OSError, TypeError) as e:
            logger.error(f"保存或序列化步骤总结至 {file_path} 失败: {e}")
            raise

    def load_step_summary(self, step_number: int) -> Optional[Dict]:
        """加载指定成功步骤的AI总结。"""
        workspace_path = self._get_workspace_path()
        successful_step_path = workspace_path / self.SUCCESSFUL_STEPS_DIR / f"step_{step_number}"
        file_path = successful_step_path / self.STEP_SUMMARY_FILENAME

        if not file_path.exists():
            logger.warning(f"未找到步骤 {step_number} 的代码总结文件。")
            return None
        
        try:
            with file_path.open('r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载步骤 {step_number} 的代码总结文件 {file_path} 失败: {e}")
            return None

    def load_successful_step_code_as_json(self, step_number: int) -> Optional[Dict[str, Any]]:
        """加载指定成功步骤的完整代码结构，并以JSON格式返回。"""
        workspace_path = self._get_workspace_path()
        successful_step_path = workspace_path / self.SUCCESSFUL_STEPS_DIR / f"step_{step_number}"

        if not successful_step_path.exists():
            logger.warning(f"未找到步骤 {step_number} 的成功代码快照。")
            return None
        
        try:
            code_json = self._read_directory_to_json(successful_step_path)
            logger.info(f"成功加载步骤 {step_number} 的代码快照作为JSON。")
            return code_json
        except Exception as e:
            logger.error(f"加载步骤 {step_number} 的成功代码快照时出错: {e}", exc_info=True)
            return None

    def load_attempt_code_as_json(self, step_number: int, attempt_number: int) -> Optional[Dict[str, Any]]:
        """加载指定尝试步骤的完整代码结构，并以JSON格式返回。"""
        attempt_path = self.get_step_attempt_path(step_number, attempt_number)

        if not attempt_path.exists():
            logger.warning(f"未找到步骤 {step_number} 尝试 {attempt_number} 的代码快照。")
            return None
        
        try:
            code_json = self._read_directory_to_json(attempt_path)
            logger.info(f"成功加载步骤 {step_number} 尝试 {attempt_number} 的代码作为JSON。")
            return code_json
        except Exception as e:
            logger.error(f"加载步骤 {step_number} 尝试 {attempt_number} 的代码时出错: {e}", exc_info=True)
            return None

    def get_successful_step_path(self, step_number: int) -> Optional[Path]:
        """获取指定成功步骤的代码快照的路径。"""
        workspace_path = self._get_workspace_path()
        successful_step_path = workspace_path / self.SUCCESSFUL_STEPS_DIR / f"step_{step_number}"
        if successful_step_path.exists() and successful_step_path.is_dir():
            return successful_step_path
        return None

    def get_latest_successful_code_path(self) -> Optional[Path]:
        """获取最新整合后的成功代码的路径。"""
        workspace_path = self._get_workspace_path()
        latest_code_path = workspace_path / self.LATEST_SUCCESSFUL_CODE_DIR
        if latest_code_path.exists() and latest_code_path.is_dir():
            return latest_code_path
        return None

    def load_latest_successful_code_as_json(self) -> Optional[Dict[str, Any]]:
        """加载最新成功代码的完整代码结构，并以JSON格式返回。"""
        latest_code_path = self.get_latest_successful_code_path()

        if not latest_code_path or not any(latest_code_path.iterdir()):
            logger.warning("最新成功代码目录不存在或为空。")
            return {"files": []} 
        
        try:
            code_json = self._read_directory_to_json(latest_code_path)
            logger.info("成功加载最新的代码快照作为JSON。")
            return code_json
        except Exception as e:
            logger.error(f"加载最新成功代码快照时出错: {e}", exc_info=True)
            return None
    
    def save_initial_idea(self, idea: str):
        workspace_path = self._get_workspace_path()
        file_path = workspace_path / self.RAW_INPUT_FILENAME
        try:
            file_path.write_text(idea, encoding='utf-8')
            logger.info(f"用户原始构想已保存至: {file_path}")
        except OSError as e:
            logger.error(f"保存用户原始构想至 {file_path} 失败: {e}")
            raise

    def save_refined_project_description(self, description_json: Dict):
        workspace_path = self._get_workspace_path()
        file_path = workspace_path / self.PROJECT_DEFINITION_FILENAME
        try:
            with file_path.open('w', encoding='utf-8') as f:
                json.dump(description_json, f, indent=4, ensure_ascii=False)
            logger.info(f"项目描述已保存至: {file_path}")
        except (OSError, TypeError) as e:
            logger.error(f"保存或序列化项目描述至 {file_path} 失败: {e}")
            raise

    def load_refined_project_description(self) -> Optional[Dict]:
        workspace_path = self._get_workspace_path()
        file_path = workspace_path / self.PROJECT_DEFINITION_FILENAME
        if not file_path.exists():
            return None
        try:
            with file_path.open('r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载项目描述文件 {file_path} 失败: {e}")
            return None

    def save_task_steps(self, task_steps_json: Dict):
        workspace_path = self._get_workspace_path()
        file_path = workspace_path / self.TASK_STEPS_FILENAME
        try:
            with file_path.open('w', encoding='utf-8') as f:
                json.dump(task_steps_json, f, indent=4, ensure_ascii=False)
            logger.info(f"任务拆分结果已保存至: {file_path}")
        except Exception as e:
            logger.error(f"保存任务拆分结果至 {file_path} 失败: {e}")
            raise

    def load_task_steps(self) -> Optional[Dict]:
        workspace_path = self._get_workspace_path()
        file_path = workspace_path / self.TASK_STEPS_FILENAME
        if not file_path.exists():
            return None
        try:
            with file_path.open('r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载任务步骤文件 {file_path} 失败: {e}")
            return None

    def get_project_definition(self) -> Optional[Dict]:
        return self.load_refined_project_description()

    def get_task_for_step(self, step_number: int) -> Optional[Dict]:
        all_tasks = self.load_task_steps()
        if all_tasks and "steps" in all_tasks:
            for task in all_tasks["steps"]:
                if task.get("step_number") == step_number:
                    return task
        return None

    def get_step_attempt_path(self, step_number: int, attempt_number: int) -> Path:
        workspace_path = self._get_workspace_path()
        attempt_path = (workspace_path / 
                        self.GENERATED_CODE_ROOT_DIR / 
                        self.STEP_ATTEMPTS_DIR_TEMPLATE.format(step_number=step_number) /
                        self.ATTEMPT_DIR_TEMPLATE.format(attempt_number=attempt_number))
        attempt_path.mkdir(parents=True, exist_ok=True)
        return attempt_path

    def save_step_code_generation_output(self, step_number: int, attempt_number: int, code_json: Dict):
        attempt_path = self.get_step_attempt_path(step_number, attempt_number)
        file_path = attempt_path / self.STEP_CODE_OUTPUT_FILENAME
        try:
            with file_path.open('w', encoding='utf-8') as f:
                json.dump(code_json, f, indent=4, ensure_ascii=False)
            logger.info(f"步骤 {step_number} (尝试 {attempt_number}) 的代码生成JSON已保存至: {file_path}")
        except Exception as e:
            logger.error(f"保存代码生成JSON至 {file_path} 失败: {e}")
            raise

    def get_project_name(self) -> Optional[str]:
        return self.project_name
    
    def save_step_execution_result(self, step_number: int, attempt_number: int, stdout: str, stderr: str, return_code: int):
        attempt_path = self.get_step_attempt_path(step_number, attempt_number)
        try:
            (attempt_path / self.EXECUTION_STDOUT_FILENAME).write_text(stdout, encoding='utf-8')
            (attempt_path / self.EXECUTION_STDERR_FILENAME).write_text(stderr, encoding='utf-8')
            result_summary = {"return_code": return_code}
            with (attempt_path / self.EXECUTION_RESULT_FILENAME).open('w', encoding='utf-8') as f:
                json.dump(result_summary, f, indent=4)
            logger.info(f"步骤 {step_number} (尝试 {attempt_number}) 的代码执行结果已保存。")
        except Exception as e:
            logger.error(f"保存代码执行结果至 {attempt_path} 失败: {e}")

    def save_dependency_install_log(self, step_number: int, attempt_number: int, stdout: str, stderr: str):
        attempt_path = self.get_step_attempt_path(step_number, attempt_number)
        log_content = f"--- STDOUT ---\n{stdout}\n\n--- STDERR ---\n{stderr}"
        try:
            (attempt_path / self.INSTALL_LOG_FILENAME).write_text(log_content, encoding='utf-8')
        except Exception as e:
            logger.error(f"保存依赖安装日志至 {attempt_path} 失败: {e}")

    def save_step_error_summary(self, step_number: int, attempt_number: int, summary: str):
        attempt_path = self.get_step_attempt_path(step_number, attempt_number)
        file_path = attempt_path / self.ERROR_SUMMARY_FILENAME
        try:
            file_path.write_text(summary, encoding='utf-8')
        except Exception as e:
            logger.error(f"保存错误摘要至 {file_path} 失败: {e}")

    def save_user_feedback(self, step_number: int, attempt_number: int, feedback: str):
        attempt_path = self.get_step_attempt_path(step_number, attempt_number)
        file_path = attempt_path / self.USER_FEEDBACK_FILENAME
        try:
            file_path.write_text(feedback, encoding='utf-8')
        except Exception as e:
            logger.error(f"保存用户反馈至 {file_path} 失败: {e}")
            
    def save_inspector_feedback(self, step_number: int, attempt_number: int, feedback: str):
        """保存检察员的反馈意见。"""
        attempt_path = self.get_step_attempt_path(step_number, attempt_number)
        file_path = attempt_path / self.INSPECTOR_FEEDBACK_FILENAME
        try:
            file_path.write_text(feedback, encoding='utf-8')
            logger.info(f"检察员反馈已保存至: {file_path}")
        except Exception as e:
            logger.error(f"保存检察员反馈至 {file_path} 失败: {e}")