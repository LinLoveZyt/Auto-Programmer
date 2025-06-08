# main.py
import logging

from auto_programmer_core import (
    ConfigManager,
    setup_logging,
    PromptManager,
    LLMInterface,
    UserInteraction,
    ProjectState,
    WorkflowController
)

logger = logging.getLogger(__name__)

def main_workflow():
    """
    主工作流函数，负责初始化和协调项目核心流程。
    """
    logger.info("Auto-Programmer 核心流程启动...")
    try:
        # 1. 初始化
        config_manager = ConfigManager() 
        log_config = config_manager.get_logging_config()
        # 确保日志文件保存在工作区内，所以先初始化ProjectState来创建工作区
        project_state = ProjectState(config_manager)
        
        # 为了让日志文件保存在项目工作区，此处调整了初始化顺序
        # 必须先创建工作区，再设置日志
        workspace_path = project_state.initialize_workspace()
        log_file_path = workspace_path / log_config.get('log_file') if log_config.get('log_file') else None
        setup_logging(log_level_str=log_config.get('level', 'INFO'), log_file=str(log_file_path) if log_file_path else None)
        logger.info("配置和日志系统初始化完成。")

        prompt_manager = PromptManager(config_manager.get_project_config().get("prompt_template_dir"))
        llm_interface = LLMInterface(config_manager.get_llm_config())
        user_interaction = UserInteraction()
        # project_state 已经提前初始化
        workflow_controller = WorkflowController(
            config_manager, prompt_manager, llm_interface, user_interaction, project_state
        )
        logger.info("所有核心组件初始化完成。")

        # 2. 规划阶段：构想 -> 澄清 -> 细化 -> 确认 -> 拆分
        clarification_success, user_answers = workflow_controller.run_clarification_phase()
        if not clarification_success:
            logger.error("项目需求澄清阶段失败。")
            return
            
        initial_success = workflow_controller.run_initial_refinement_phase(workspace_path, user_answers) # 传入澄清后的回答
        if not initial_success:
            logger.error("项目初始构想细化或环境设置阶段失败。")
            return

        iteration_success = workflow_controller.run_project_definition_iteration_phase()
        if not iteration_success:
            logger.error("项目定义迭代确认阶段失败。")
            return
        
        decomposition_success = workflow_controller.run_task_decomposition_phase()
        if not decomposition_success:
            logger.error("任务拆分阶段失败。")
            return
        
        logger.info("规划阶段（构想->确认->拆分）全部成功。")

        # 3. 执行阶段：代码生成 -> 构建 -> 安装 -> 执行
        execution_success = workflow_controller.run_steps_execution_phase()
        
        # 4. 收尾阶段：清理与归档
        if execution_success:
            logger.info("代码生成与执行阶段成功。进入最终收尾阶段。")
            workflow_controller.run_finalization_phase()
        else:
            logger.error("代码生成与执行阶段失败。跳过收尾阶段。")

    except Exception as e:
        logger.critical(f"主流程中发生未捕获的严重错误: {e}", exc_info=True)
        print(f"发生严重错误，程序终止。详情请查看日志。错误: {e}")
    finally:
        logger.info("Auto-Programmer 核心流程结束。")

# 为了在main函数外部也能调用，调整了函数定义
def main():
    main_workflow()

if __name__ == "__main__":
    main()