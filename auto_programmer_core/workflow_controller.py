# auto_programmer_core/workflow_controller.py
import logging
import json
import shutil 
import sys
from typing import Optional, Tuple
from pathlib import Path
from collections import deque

from rich import print as rprint
from rich.panel import Panel

from .config_manager import ConfigManager
from .prompt_manager import PromptManager
from .llm_interface import LLMInterface
from .user_interaction import UserInteraction
from .project_state import ProjectState
from .project_builder import ProjectBuilder
from .step_handler import StepHandler
from .environment_manager import EnvironmentManager
# --- 新增导入 ---
from .code_runner import CodeRunner

logger = logging.getLogger(__name__)

class WorkflowController:
    """
    协调项目的各个阶段流程。
    """
    def __init__(self,
                 config_manager: ConfigManager,
                 prompt_manager: PromptManager,
                 llm_interface: LLMInterface,
                 user_interaction: UserInteraction,
                 project_state: ProjectState):
        self.config_manager = config_manager
        self.prompt_manager = prompt_manager
        self.llm_interface = llm_interface
        self.user_interaction = user_interaction
        self.project_state = project_state

        self.env_config = config_manager.get_environment_config()
        self.environment_manager = EnvironmentManager(self.env_config)
        self.current_env_name: Optional[str] = None
        
        self.last_main_executable: Optional[str] = None
        
        logger.info("WorkflowController 初始化完成。")

    # ... (run_clarification_phase, run_initial_refinement_phase 等方法保持不变) ...
    def setup_environment(self) -> bool:
        """在工作流开始时设置项目专用的环境"""
        project_name = self.project_state.get_project_name()
        project_workspace = self.project_state.current_workspace
        if not project_name or not project_workspace:
            logger.error("无法获取项目名称或工作区，无法设置环境。")
            return False
        
        self.current_env_name = project_name
        
        try:
            return self.environment_manager.setup_project_environment(
                env_name=self.current_env_name,
                project_workspace=project_workspace
            )
        except RuntimeError as e:
            logger.critical(f"环境设置失败: {e}", exc_info=True)
            print(f"发生严重错误: {e}")
            return False

    def run_clarification_phase(self) -> Tuple[bool, str]:
        """
        执行需求澄清阶段。
        """
        logger.info("开始执行需求澄清阶段...")
        try:
            user_idea = self.user_interaction.get_initial_project_idea()
            if not user_idea:
                logger.warning("用户未提供项目构想，终止流程。")
                print("未提供项目构想，流程结束。")
                return False, ""
            
            self.project_state.save_initial_idea(user_idea)

            prompt = self.prompt_manager.load_and_format_prompt(
                "clarification_questions",
                user_idea=user_idea,
                os_info=sys.platform,
                python_version=self.env_config.get("python_version")
            )

            llm_response = self.llm_interface.generate_response(prompt, expect_json=True)

            if not isinstance(llm_response, dict) or "questions" not in llm_response:
                logger.warning(f"AI未能生成有效的澄清问题JSON。响应: {llm_response}。将跳过此阶段。")
                return True, "用户未提供补充信息（AI未能生成问题）。"
            
            user_answers = self.user_interaction.get_clarifying_answers(llm_response)
            return True, user_answers

        except Exception as e:
            logger.exception(f"在需求澄清阶段发生错误: {e}")
            print(f"发生错误: {e}. 请检查日志。")
            return False, ""

    def run_initial_refinement_phase(self, workspace_path: Path, user_answers: str) -> bool:
        """
        执行项目初始构想细化与环境设置阶段。
        """
        logger.info("开始执行项目初始构想细化阶段...")
        try:
            logger.info(f"项目工作区已在 {workspace_path} 初始化。")

            if not self.setup_environment():
                logger.critical("项目环境设置失败，流程终止。")
                return False
            
            user_idea = (self.project_state._get_workspace_path() / self.project_state.RAW_INPUT_FILENAME).read_text(encoding='utf-8')

            formatted_prompt = self.prompt_manager.load_and_format_prompt(
                "initial_refinement", 
                user_idea=user_idea,
                user_answers=user_answers
            )

            print("\n正在结合您的构想和补充信息，进行项目规划，请稍候...")
            logger.info("正在请求LLM细化项目构想...")
            llm_response = self.llm_interface.generate_response(formatted_prompt, expect_json=True)

            if llm_response and isinstance(llm_response, dict) and "error" not in llm_response:
                self.project_state.save_refined_project_description(llm_response)
                self.user_interaction.display_project_description(llm_response)
                logger.info("项目初始构想细化阶段成功完成。")
                return True
            else:
                logger.error(f"LLM未能返回有效的JSON项目描述。响应: {llm_response}")
                print("抱歉，无法从AI获取有效的项目细化描述。")
                return False

        except Exception as e:
            logger.exception(f"在项目初始构想细化阶段发生未预料的错误: {e}")
            print(f"发生严重错误: {e}. 请检查日志。")
            return False

    def run_project_definition_iteration_phase(self) -> bool:
        """
        执行项目定义的迭代确认阶段。
        """
        logger.info("开始项目定义迭代确认阶段...")
        current_description = self.project_state.load_refined_project_description()
        if not current_description:
            logger.error("无法加载初始项目描述，无法开始迭代。")
            return False

        while True:
            is_satisfied = self.user_interaction.get_confirmation("\n您对以上项目描述满意吗？")

            if is_satisfied:
                logger.info("用户确认项目描述。")
                self.project_state.save_refined_project_description(current_description)
                print("\n✅ 项目描述已最终确认！")
                return True

            feedback = self.user_interaction.get_feedback("请提供您的修改意见：")
            if not feedback.strip():
                logger.warning("用户未提供有效反馈，迭代中止，接受当前版本。")
                return True

            prompt = self.prompt_manager.load_and_format_prompt(
                "refinement_iteration",
                previous_description_json=json.dumps(current_description, ensure_ascii=False, indent=4),
                user_feedback=feedback
            )
            
            print("\n正在根据您的反馈更新项目描述，请稍候...")
            llm_response = self.llm_interface.generate_response(prompt, expect_json=True)

            if llm_response and isinstance(llm_response, dict) and "error" not in llm_response:
                current_description = llm_response
                logger.info("LLM返回了修改后的项目描述。")
                print("项目描述已更新。请再次审阅：")
                self.user_interaction.display_project_description(current_description)
            else:
                logger.error("LLM未能返回有效的修改版JSON项目描述。")
                print("抱歉，AI未能根据您的反馈有效修改项目描述。")

    def run_task_decomposition_phase(self) -> bool:
        """
        执行任务拆分阶段。
        """
        logger.info("开始任务拆分阶段...")
        confirmed_description = self.project_state.load_refined_project_description()
        if not confirmed_description:
            logger.error("未能加载已确认的项目描述，无法进行任务拆分。")
            return False

        prompt = self.prompt_manager.load_and_format_prompt(
            "task_decomposition",
            confirmed_project_description_json=json.dumps(confirmed_description, ensure_ascii=False, indent=4)
        )
        
        print("\n项目描述已确认，正在进行任务拆分，请稍候...")
        logger.info("请求LLM进行任务拆分...")
        llm_response = self.llm_interface.generate_response(prompt, expect_json=True)

        if llm_response and isinstance(llm_response, dict) and "steps" in llm_response:
            self.project_state.save_task_steps(llm_response)
            self.user_interaction.display_task_steps(llm_response)
            logger.info("任务拆分阶段成功完成。")
            return True
        else:
            logger.error(f"LLM未能返回有效的JSON任务步骤。响应: {llm_response}")
            print("抱歉，无法从AI获取有效的任务拆分结果。")
            return False

    def run_steps_execution_phase(self) -> bool:
        """
        【已重构】根据任务依赖图 (DAG) 执行所有已拆分的开发步骤。
        采用拓扑排序的执行逻辑。
        """
        logger.info("--- 开始进入基于依赖图的代码生成与执行阶段 ---")
        
        tasks_data = self.project_state.load_task_steps()
        if not tasks_data or not tasks_data.get("steps"):
            logger.warning("未找到任何任务步骤，跳过代码执行阶段。")
            return True

        if not self.current_env_name:
            logger.error("当前项目环境名称未设置，无法执行步骤。")
            return False

        execution_config = self.config_manager.get_execution_config()
        project_builder = ProjectBuilder()

        # --- 修改开始: 实例化并传递 CodeRunner ---
        code_runner = CodeRunner(
            timeout=execution_config.get("script_timeout_seconds", 300),
            env_config=self.env_config
        )
        step_handler = StepHandler(
            project_state=self.project_state,
            llm_interface=self.llm_interface,
            prompt_manager=self.prompt_manager,
            project_builder=project_builder,
            environment_manager=self.environment_manager,
            user_interaction=self.user_interaction,
            code_runner=code_runner,  # 传递实例
            env_name=self.current_env_name,
            max_attempts=execution_config.get("max_step_attempts", 3),
            env_manager_type=self.env_config.get("env_manager", "conda")
        )
        # --- 修改结束 ---

        steps = {step['step_number']: step for step in tasks_data['steps']}
        adj_list = {step_num: [] for step_num in steps}
        in_degree = {step_num: 0 for step_num in steps}

        for step_num, step_data in steps.items():
            dependencies = step_data.get('dependencies', [])
            in_degree[step_num] = len(dependencies)
            for dep_num in dependencies:
                if dep_num in adj_list:
                    adj_list[dep_num].append(step_num)
                else:
                    logger.error(f"任务 {step_num} 依赖一个不存在的任务 {dep_num}。流程终止。")
                    print(f"❌ 任务定义错误：任务 {step_num} 的依赖 {dep_num} 不存在。")
                    return False
        
        queue = deque([step_num for step_num, degree in in_degree.items() if degree == 0])
        completed_steps = set()
        total_steps = len(steps)

        logger.info(f"任务依赖图解析完成。拓扑排序开始，初始队列: {list(queue)}")

        while queue:
            step_number = queue.popleft()
            step_task = steps[step_number]
            
            progress_title = f"[步骤 {step_number}/{total_steps}] {step_task.get('step_title', '')}"
            rprint(Panel(f"[bold cyan]{progress_title}[/bold cyan]", border_style="cyan", expand=True))
            
            result, main_executable = step_handler.execute_step(step_number, step_task, completed_steps)
            
            if result == 'success':
                completed_steps.add(step_number)
                if main_executable:
                    self.last_main_executable = main_executable
                
                for dependent_step_num in adj_list[step_number]:
                    in_degree[dependent_step_num] -= 1
                    if in_degree[dependent_step_num] == 0:
                        queue.append(dependent_step_num)
                        logger.info(f"任务 {dependent_step_num} 的所有依赖已完成，加入待执行队列。")

            elif result == 'aborted' or result == 'skipped':
                message = "执行" if result == 'aborted' else "跳过"
                logger.error(f"步骤 {step_number} 的{message}导致流程终止。")
                print(f"❌ 步骤 {step_number} 已被{message}，项目流程终止。")
                return len(completed_steps) > 0

        if len(completed_steps) == total_steps:
            logger.info("--- 所有开发步骤均已根据依赖图成功执行完毕 ---")
            print("\n🎉 恭喜！项目所有开发步骤均已成功完成！")
            return True
        else:
            logger.error(f"流程结束，但并非所有任务都已完成。已完成: {len(completed_steps)}/{total_steps}。可能存在循环依赖。")
            print(f"❌ 项目流程异常结束。已完成 {len(completed_steps)}/{total_steps} 个。请检查日志（可能存在循环依赖）。")
            return False

    def run_finalization_phase(self):
        """
        执行项目完成后的最终收尾阶段。
        """
        logger.info("--- 开始进入项目最终收尾阶段 ---")
        rprint(Panel("[bold green]项目收尾[/bold green]", title="🏁", border_style="green", expand=True))

        project_fully_completed = False
        tasks_data = self.project_state.load_task_steps()
        if tasks_data and tasks_data.get("steps"):
            # A bit of a hacky way to check, relies on the last state of completed_steps from the execution phase
            # A better way would be to properly store the final state. For now, this is an approximation.
             final_code_path = self.project_state.get_latest_successful_code_path()
             if final_code_path and any(final_code_path.iterdir()):
                 project_fully_completed = True


        if self.current_env_name and self.project_state.current_workspace:
            env_manager_type = self.env_config.get("env_manager", "conda")
            
            choice, new_name = self.user_interaction.prompt_environment_cleanup_choice(
                self.current_env_name, env_manager_type
            )
            
            if choice == "delete":
                self.environment_manager.delete_environment(
                    self.current_env_name, self.project_state.current_workspace
                )
            elif choice == "rename" and new_name:
                self.environment_manager.rename_environment(
                    self.current_env_name, new_name, self.project_state.current_workspace
                )
            else: 
                print(f"环境 '{self.current_env_name}' 已保留。")
        
        self.project_state.archive_project()
        
        final_code_path = self.project_state.get_latest_successful_code_path()
        if final_code_path and any(final_code_path.iterdir()):
            env_to_display = self.current_env_name or self.project_state.get_project_name()
            
            guidance_message = (
                f"[bold]项目最终产物指引[/bold]\n\n"
                f"✅ [bold green]最终代码已生成完毕！[/bold green]\n\n"
                f"📂 [bold]代码路径:[/bold]\n[cyan]{final_code_path.resolve()}[/cyan]\n"
            )
            if self.last_main_executable:
                run_command = ""
                if self.env_config.get("env_manager") == "conda":
                    run_command = f"conda run -n {env_to_display} python {self.last_main_executable}"
                else: 
                    py_exec = ".venv/Scripts/python.exe" if sys.platform == "win32" else "./.venv/bin/python"
                    run_command = f"cd {final_code_path.resolve()} && {py_exec} {self.last_main_executable}"

                guidance_message += f"\n🚀 [bold]建议运行命令 (在新终端中执行):[/bold]\n[cyan]{run_command}[/cyan]\n"
            
            rprint(Panel(guidance_message, title="💡 使用指南", border_style="yellow"))
        
        print("\n项目开发流程已全部完成。感谢使用！")
        logger.info("--- 项目最终收尾阶段完成 ---")