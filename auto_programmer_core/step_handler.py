# auto_programmer_core/step_handler.py
import logging
import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
import hashlib

from .user_interaction import UserInteraction
from .project_state import ProjectState
from .llm_interface import LLMInterface
from .prompt_manager import PromptManager
from .project_builder import ProjectBuilder
from .environment_manager import EnvironmentManager
from .code_runner import CodeRunner

logger = logging.getLogger(__name__)

class StepHandler:
    """
    负责处理单个开发步骤的执行逻辑，包含自动化测试、错误处理和用户反馈的迭代循环。
    """
    def __init__(self,
                 project_state: ProjectState,
                 llm_interface: LLMInterface,
                 prompt_manager: PromptManager,
                 project_builder: ProjectBuilder,
                 environment_manager: EnvironmentManager,
                 user_interaction: UserInteraction,
                 code_runner: CodeRunner,
                 env_name: str,
                 max_attempts: int,
                 env_manager_type: str):
        self.project_state = project_state
        self.llm_interface = llm_interface
        self.prompt_manager = prompt_manager
        self.project_builder = project_builder
        self.environment_manager = environment_manager
        self.user_interaction = user_interaction
        self.code_runner = code_runner
        self.env_name = env_name
        self.max_attempts = max_attempts
        self.env_manager_type = env_manager_type
        logger.info(f"StepHandler 初始化完成，每个步骤最多尝试 {self.max_attempts} 次。")


    def _validate_initial_code_response(self, response: Dict[str, Any]) -> Tuple[bool, str]:
        if not isinstance(response, dict): return False, "LLM响应不是一个有效的JSON对象。"
        if "files" not in response: return False, "JSON响应中缺少'files'键。"
        if "usage_guide" not in response: return False, "JSON响应中缺少'usage_guide'对象。"
        return True, ""

    def _validate_modification_instructions_response(self, response: Dict[str, Any]) -> Tuple[bool, str]:
        if not isinstance(response, dict): return False, "LLM响应不是一个有效的JSON对象。"
        if "modifications" not in response: return False, "JSON响应中缺少'modifications'键。"
        if "usage_guide" not in response: return False, "JSON响应中缺少'usage_guide'对象。"
        return True, ""


    def execute_step(self, step_number: int, step_task: Dict[str, Any], completed_steps: set) -> Tuple[str, Optional[str]]:
        logger.info(f"--- 开始执行开发步骤 {step_number} (已完成步骤: {completed_steps}) ---")
        dependencies = step_task.get("dependencies", [])
        step_type = step_task.get("step_type", "feature_development")
        if not dependencies and step_type == "feature_development":
            return self._execute_initial_generation_step(step_number, step_task)
        else:
            return self._execute_modification_step(step_number, step_task, completed_steps)

    def _run_unit_tests(self, step_number: int, attempt_number: int, attempt_path: Path, tests_to_run: List[str]) -> Tuple[bool, str]:
        if not tests_to_run:
            logger.info(f"步骤 {step_number} 未指定自动化测试，跳过此环节。")
            return True, ""
        project_workspace = self.project_state.current_workspace
        if not project_workspace:
             return False, "内部错误：项目工作区未找到，无法运行测试。"
        stdout, stderr, return_code = self.code_runner.run_tests(
            test_paths=tests_to_run,
            env_name=self.env_name,
            cwd=attempt_path,
            project_workspace=project_workspace
        )
        if return_code == 0:
            print("✅ 自动化测试通过！")
            logger.info(f"步骤 {step_number}, 尝试 {attempt_number} 的自动化测试成功。")
            return True, ""
        else:
            print("❌ 自动化测试失败，AI将尝试自动修复...")
            logger.warning(f"步骤 {step_number}, 尝试 {attempt_number} 的自动化测试失败。返回码: {return_code}")
            test_output = (f"--- STDOUT ---\n{stdout}\n\n--- STDERR ---\n{stderr}").strip()
            ai_feedback = (
                "你生成的代码未能通过自动化测试。请分析下面的 `pytest` 输出，并修正你的代码（包括功能代码和测试代码）。"
                f"错误日志:\n---\n{test_output}\n---"
            )
            return False, ai_feedback

    def _run_inspection(self, step_number: int, attempt_number: int, completed_steps: set) -> Tuple[bool, str]:
        print("🕵️  代码已生成，正在提交给“代码审查员 & 架构守护者”进行审查...")
        logger.info(f"开始对步骤 {step_number} 尝试 {attempt_number} 的代码进行架构性审查。")
        project_definition = self.project_state.get_project_definition()
        step_task = self.project_state.get_task_for_step(step_number)
        step_code_json = self.project_state.load_attempt_code_as_json(step_number, attempt_number)
        architecture_notes = self.project_state.load_architecture_notes()
        if not all([project_definition, step_task, step_code_json]):
            return False, "内部错误：无法加载审查所需的数据。"
        previous_steps_summaries = []
        if completed_steps:
            for i in sorted(list(completed_steps)):
                summary = self.project_state.load_step_summary(i)
                if summary:
                    previous_steps_summaries.append({"step_number": i, "summary": summary})
        try:
            prompt = self.prompt_manager.load_and_format_prompt(
                "code_inspector",
                project_definition_json=json.dumps(project_definition, ensure_ascii=False, indent=2),
                previous_steps_summary_json=json.dumps(previous_steps_summaries, ensure_ascii=False, indent=2),
                architecture_notes=architecture_notes,
                step_number=step_number,
                step_description_json=json.dumps(step_task, ensure_ascii=False, indent=2),
                step_code_json=json.dumps(step_code_json, ensure_ascii=False, indent=2)
            )
            inspector_response = self.llm_interface.generate_response(prompt, expect_json=True)
            if not isinstance(inspector_response, dict) or "approved" not in inspector_response:
                return False, "检察员返回了无效的响应格式，请修正输出的JSON结构。"
            is_approved = inspector_response.get("approved", False)
            feedback = inspector_response.get("feedback", "")
            notes_to_add = inspector_response.get("architecture_notes_to_add", "")
            self.project_state.save_inspector_feedback(step_number, attempt_number, feedback if feedback else "审查通过")
            if is_approved:
                print("✅ 检察员审查通过！")
                logger.info(f"审查通过: 步骤 {step_number}, 尝试 {attempt_number}")
                if notes_to_add:
                    print("🧠 架构守护者记录了新的设计决策。")
                    self.project_state.save_architecture_notes(notes_to_add)
                return True, ""
            else:
                print("❌ 检察员发现问题，准备重新生成代码...")
                return False, feedback or "代码审查未通过，但检察员未提供具体反馈。"
        except Exception as e:
            logger.error(f"代码审查流程中发生严重错误: {e}", exc_info=True)
            return False, f"代码审查流程中发生内部错误: {e}"

    def _execute_initial_generation_step(self, step_number: int, step_task: Dict[str, Any]) -> Tuple[str, Optional[str]]:
        logger.info(f"执行初始/无依赖代码生成流程 (步骤 {step_number})")
        project_definition = self.project_state.get_project_definition()
        architecture_notes = self.project_state.load_architecture_notes()
        if not all([project_definition, step_task]):
            return 'aborted', None
        attempt_number = 0
        cumulative_feedback: List[str] = [] 
        while attempt_number < self.max_attempts:
            attempt_number += 1
            print(f"\n>>>>> 步骤 {step_number} (初始生成), 尝试第 {attempt_number}/{self.max_attempts} 次 <<<<<")
            logger.info(f"--- Step {step_number} (Initial), Attempt {attempt_number} ---")
            try:
                feedback_section = ""
                if cumulative_feedback:
                    feedback_section = "你之前的尝试失败了。请分析下面的失败历史，修正你的代码...\n\n" + "\n---\n".join(cumulative_feedback)
                prompt = self.prompt_manager.load_and_format_prompt(
                    'code_generation_step1',
                    project_definition_json=json.dumps(project_definition, ensure_ascii=False, indent=2),
                    architecture_notes=architecture_notes,
                    step_description_json=json.dumps(step_task, ensure_ascii=False, indent=2),
                    feedback_section=feedback_section
                )
                llm_response = self.llm_interface.generate_response(prompt, expect_json=True)
                is_valid, error_msg = self._validate_initial_code_response(llm_response)
                if not is_valid:
                    cumulative_feedback.append(f"JSON格式错误: {error_msg}")
                    continue
                step_attempt_path = self.project_state.get_step_attempt_path(step_number, attempt_number)
                self.project_state.save_step_code_generation_output(step_number, attempt_number, llm_response)
                build_success = self.project_builder.build_project_structure(
                    step_attempt_path,
                    llm_response.get("files", [])
                )
                if not build_success:
                    cumulative_feedback.append("无法根据你返回的JSON构建项目文件结构。")
                    continue
                action, result_payload = self._build_and_verify(
                    step_number=step_number,
                    attempt_number=attempt_number,
                    step_attempt_path=step_attempt_path,
                    llm_response=llm_response,
                    completed_steps=set()
                )
                if action == 'success':
                    return 'success', result_payload
                elif action == 'failure' and result_payload:
                    cumulative_feedback.append(result_payload)
                else: 
                    return action, result_payload
            except Exception as e:
                logger.error(f"执行初始生成步骤 {step_number} 期间发生严重错误: {e}", exc_info=True)
                return 'aborted', None
        return 'aborted', None

    def _execute_modification_step(self, step_number: int, step_task: Dict[str, Any], completed_steps: set) -> Tuple[str, Optional[str]]:
        logger.info(f"执行代码修改流程 (步骤 {step_number})")
        project_definition = self.project_state.get_project_definition()
        base_code_path = self.project_state.get_latest_successful_code_path()
        last_step_code_json = self.project_state.load_latest_successful_code_as_json()
        architecture_notes = self.project_state.load_architecture_notes()
        if not all([project_definition, step_task, base_code_path, last_step_code_json is not None]):
            return 'aborted', None
        previous_steps_summaries = []
        if completed_steps:
            for i in sorted(list(completed_steps)):
                summary = self.project_state.load_step_summary(i)
                if summary:
                    previous_steps_summaries.append({"step_number": i, "summary": summary})
        attempt_number = 0
        cumulative_feedback: List[str] = [] 
        while attempt_number < self.max_attempts:
            attempt_number += 1
            print(f"\n>>>>> 步骤 {step_number} (代码修改), 尝试第 {attempt_number}/{self.max_attempts} 次 <<<<<")
            logger.info(f"--- Step {step_number} (Modification), Attempt {attempt_number} ---")
            try:
                feedback_section = ""
                if cumulative_feedback:
                    feedback_section = "你之前的尝试失败了。请分析下面的失败历史...\n\n" + "\n---\n".join(cumulative_feedback)
                last_successful_step_number = max(completed_steps) if completed_steps else 0
                prompt = self.prompt_manager.load_and_format_prompt(
                    'code_modification',
                    project_definition_json=json.dumps(project_definition, ensure_ascii=False, indent=2),
                    architecture_notes=architecture_notes,
                    previous_steps_summary_json=json.dumps(previous_steps_summaries, ensure_ascii=False, indent=2),
                    last_successful_step_number=last_successful_step_number,
                    last_step_code_json=json.dumps(last_step_code_json, ensure_ascii=False, indent=2),
                    step_number=step_number,
                    step_description_json=json.dumps(step_task, ensure_ascii=False, indent=2),
                    feedback_section=feedback_section
                )
                modification_instructions = self.llm_interface.generate_response(prompt, expect_json=True)
                is_valid, error_msg = self._validate_modification_instructions_response(modification_instructions)
                if not is_valid:
                    cumulative_feedback.append(f"JSON格式错误: {error_msg}")
                    continue
                step_attempt_path = self.project_state.get_step_attempt_path(step_number, attempt_number)
                self.project_state.save_step_code_generation_output(step_number, attempt_number, modification_instructions)
                build_success = self.project_builder.apply_modifications(
                    base_path=base_code_path,
                    target_path=step_attempt_path,
                    instructions=modification_instructions.get("modifications", [])
                )
                if not build_success:
                    cumulative_feedback.append("应用你提供的修改指令失败。")
                    continue
                action, result_payload = self._build_and_verify(
                    step_number=step_number,
                    attempt_number=attempt_number,
                    step_attempt_path=step_attempt_path,
                    llm_response=modification_instructions,
                    completed_steps=completed_steps
                )
                if action == 'success':
                    return 'success', result_payload
                elif action == 'failure' and result_payload:
                    cumulative_feedback.append(result_payload)
                else:
                    return action, result_payload
            except Exception as e:
                logger.error(f"执行修改步骤 {step_number} 期间发生严重错误: {e}", exc_info=True)
                return 'aborted', None
        return 'aborted', None
    
    def _sanitize_dependency_file(self, dependency_file_path: Path):
        """
        读取依赖文件并移除不应存在的Python标准库模块。
        """
        if not dependency_file_path.exists():
            return

        # --- 修改开始: 新增'unittest'到标准库列表 ---
        STANDARD_LIBS = {
            "sqlite3", "os", "sys", "json", "re", "datetime", "pathlib", "logging",
            "threading", "multiprocessing", "argparse", "collections", "subprocess",
            "shutil", "glob", "math", "random", "time", "uuid", "configparser",
            "hashlib", "tempfile", "unittest"
        }
        # --- 修改结束 ---

        try:
            lines = dependency_file_path.read_text(encoding='utf-8').splitlines()
            original_count = len(lines)
            sanitized_lines = [
                line for line in lines if line.strip() and not any(
                    line.strip().lower().startswith(lib) for lib in STANDARD_LIBS
                )
            ]
            if len(sanitized_lines) < original_count:
                removed_count = original_count - len(sanitized_lines)
                logger.warning(
                    f"自动修正依赖文件: 从 '{dependency_file_path.name}' 中移除了 {removed_count} 个不应存在的标准库。"
                )
                print(f"⚠️  自动修正：检测到AI将标准库（如 unittest）错误地写入依赖文件，已自动移除。")
                dependency_file_path.write_text("\n".join(sanitized_lines) + "\n", encoding='utf-8')
        except Exception as e:
            logger.error(f"清理依赖文件 '{dependency_file_path}' 时出错: {e}", exc_info=True)

    def _build_and_verify(self, step_number, attempt_number, step_attempt_path, llm_response, completed_steps) -> Tuple[str, Optional[str]]:
        is_approved, inspector_feedback = self._run_inspection(step_number, attempt_number, completed_steps)
        if not is_approved:
            return 'failure', f"【代码检察员反馈】:\n{inspector_feedback}"
        project_workspace = self.project_state.current_workspace
        if not project_workspace: return 'aborted', "项目工作区未找到"
        dependency_file_name = llm_response.get("dependency_file") or "requirements.txt"
        requirements_file_path = step_attempt_path / dependency_file_name
        if requirements_file_path.exists():
            self._sanitize_dependency_file(requirements_file_path)
            if requirements_file_path.stat().st_size > 0:
                install_success, stdout, stderr = self.environment_manager.install_dependencies(
                    project_step_path=step_attempt_path, env_name=self.env_name, project_workspace=project_workspace, dependency_filename=dependency_file_name
                )
                self.project_state.save_dependency_install_log(step_number, attempt_number, stdout, stderr)
                if not install_success:
                    ai_feedback = f"依赖安装失败。请修正 `{dependency_file_name}`。错误日志:\n---\n{stderr}\n---"
                    print(f"❌ 依赖安装失败，AI将尝试自动修复...")
                    return 'failure', ai_feedback
        else:
            logger.info(f"无依赖文件 '{requirements_file_path.name}'，跳过安装。")
        tests_to_run = llm_response.get("tests_to_run", [])
        tests_passed, test_feedback = self._run_unit_tests(step_number, attempt_number, step_attempt_path, tests_to_run)
        if not tests_passed:
            return 'failure', test_feedback
        usage_guide = llm_response.get("usage_guide", {})
        step_task = self.project_state.get_task_for_step(step_number)
        action, feedback = self.user_interaction.prompt_for_manual_execution(
            step_task=step_task,
            usage_guide=usage_guide,
            attempt_path=step_attempt_path,
            env_name=self.env_name,
            env_manager=self.env_manager_type,
            tests_passed=bool(tests_to_run)
        )
        if action == 'success':
            self.project_state.mark_step_as_successful(step_number, step_attempt_path)
            print("\n✅ 此步骤已根据您的确认完成。正在为下一步生成代码总结...")
            if not self._summarize_successful_step(step_number):
                print("⚠️ 未能为该成功步骤生成代码总结。")
            return 'success', llm_response.get("main_executable")
        if feedback:
            self.project_state.save_user_feedback(step_number, attempt_number, feedback)
            return "failure", f"【用户反馈】:\n{feedback}"
        else:
            return action, None

    def _summarize_successful_step(self, step_number: int) -> bool:
        logger.info(f"为成功的步骤 {step_number} 生成代码总结...")
        project_def = self.project_state.get_project_definition()
        step_code_json = self.project_state.load_successful_step_code_as_json(step_number)
        if not project_def or not step_code_json:
            return False
        try:
            prompt = self.prompt_manager.load_and_format_prompt(
                "code_summary", 
                project_definition_json=json.dumps(project_def, ensure_ascii=False, indent=2), 
                step_number=step_number, 
                step_code_json=json.dumps(step_code_json, ensure_ascii=False, indent=2)
            )
            summary_response = self.llm_interface.generate_response(prompt, expect_json=True)
            if isinstance(summary_response, dict) and "error" not in summary_response:
                self.project_state.save_step_summary(step_number, summary_response)
                return True
            else:
                return False
        except Exception as e:
            logger.error(f"准备或执行代码总结时失败: {e}", exc_info=True)
            return False