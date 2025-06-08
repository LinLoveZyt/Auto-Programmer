# auto_programmer_core/user_interaction.py
import json
import logging
from typing import Dict, Tuple, Optional, List
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown
from rich import print as rprint

logger = logging.getLogger(__name__)

class UserInteraction:
    """
    负责处理与用户的交互，包括获取输入和显示信息。
    """
    def __init__(self):
        self.console = Console()
    
    # ... (get_initial_project_idea, get_clarifying_answers 等方法保持不变) ...
    def get_initial_project_idea(self) -> str:
        """
        从命令行获取用户的初始项目构想。
        """
        self.console.print(Panel("[bold cyan]欢迎使用 Auto-Programmer！[/bold cyan]", title="🚀", border_style="green"))
        self.console.print("请输入您的项目初始构想（例如：'我想做一个能监控网站内容变化的工具'）：", style="bold")
        user_idea = input("> ")
        logger.info(f"获取到用户的初始项目构想: {user_idea}")
        return user_idea

    def get_clarifying_answers(self, questions_json: Dict) -> str:
        """
        向用户展示AI生成的澄清问题，并获取用户的回答。
        """
        self.console.print(Panel("[bold yellow]AI需要更多信息[/bold yellow]", title="🤔", title_align="left", border_style="yellow"))
        self.console.print("为了更好地理解您的需求，AI提出以下问题，请您回答：")
        
        try:
            questions = questions_json.get("questions", [])
            for i, question in enumerate(questions, 1):
                self.console.print(f"[bold]问题 {i}:[/bold] {question}")

            self.console.print("\n请在下方输入您的回答（可以输入多行，输入 'done' 并按回车结束）：", style="bold")
            
            lines = []
            while True:
                line = input()
                if line.strip().lower() == 'done':
                    break
                lines.append(line)
            
            user_answers = "\n".join(lines)
            if not user_answers:
                user_answers = "用户未提供额外信息。"
                self.console.print("您没有提供额外信息，将基于原始构想继续。", style="italic dim")

            logger.info(f"获取到用户对澄清问题的回答:\n{user_answers}")
            return user_answers
        except Exception as e:
            logger.error(f"处理澄清问题时出错: {e}")
            return "用户交互阶段出现错误。"


    def display_project_description(self, description_json: Dict) -> None:
        """
        友好地向用户展示LLM生成的项目描述。
        """
        try:
            formatted_json = json.dumps(description_json, indent=4, ensure_ascii=False)
            syntax = Syntax(formatted_json, "json", theme="monokai", line_numbers=True, word_wrap=True)
            panel = Panel(syntax, title="[bold magenta]项目构想细化结果[/bold magenta]", title_align="left", border_style="magenta")
            self.console.print(panel)
            logger.info("已向用户展示项目描述。")
        except Exception as e:
            logger.error(f"展示项目描述时发生错误: {e}")
            self.console.print("错误：无法格式化项目描述。请查看日志获取详情。", style="bold red")

    def get_confirmation(self, prompt_message: str) -> bool:
        """
        向用户提问并获取是/否的确认。
        """
        while True:
            rprint(f"[bold yellow]{prompt_message} (y/n):[/bold yellow]", end=" ")
            response = input().strip().lower()
            if response == 'y':
                logger.info(f"用户对于 '{prompt_message}' 回复 '是'")
                return True
            elif response == 'n':
                logger.info(f"用户对于 '{prompt_message}' 回复 '否'")
                return False
            else:
                rprint("[bold red]无效输入，请输入 'y' 或 'n'。[/bold red]")

    def get_feedback(self, prompt_message: str) -> str:
        """
        获取用户不满意时的具体原因/修改意见。
        """
        self.console.print(prompt_message, style="bold")
        feedback = input("> ")
        logger.info(f"获取到用户的反馈: {feedback}")
        return feedback

    def display_task_steps(self, task_steps_json: Dict) -> None:
        """
        友好地向用户展示LLM生成的任务步骤。
        """
        try:
            formatted_json = json.dumps(task_steps_json, indent=4, ensure_ascii=False)
            syntax = Syntax(formatted_json, "json", theme="monokai", line_numbers=True, word_wrap=True)
            panel = Panel(syntax, title="[bold blue]项目任务拆分结果[/bold blue]", title_align="left", border_style="blue")
            self.console.print(panel)
            logger.info("已向用户展示任务步骤。")
        except Exception as e:
            logger.error(f"展示任务步骤时发生错误: {e}")
            self.console.print("错误：无法格式化任务步骤。请查看日志获取详情。", style="bold red")

    def prompt_for_manual_execution(self, step_task: Dict, usage_guide: Dict, attempt_path: Path, env_name: str, env_manager: str, tests_passed: bool = False) -> Tuple[str, Optional[str]]:
        """
        向用户展示手动执行指南，并获取执行结果的反馈。
        返回 (action, feedback), action可以是 'success', 'failure', 'skip', 'abort'
        """
        ai_command = usage_guide.get('command', 'AI未能提供运行指令。')
        
        # --- 修改开始: 增加测试通过的提示 ---
        test_status_message = ""
        if tests_passed:
            test_status_message = "[bold green]✅ 自动化单元测试已通过。[/bold green]\n\n"
        # --- 修改结束 ---

        rprint(Panel(
            f"{test_status_message}" # 新增
            f"[bold]🎯 任务目标:[/bold] {step_task.get('step_title', 'N/A')}\n\n"
            f"[bold]🤖 AI 提供的预期效果:[/bold]\n{usage_guide.get('description', 'AI未能提供预期效果描述。')}",
            title="[bold green]请手动测试代码[/bold green]",
            border_style="green",
            title_align="left"
        ))

        rprint("\n[bold]⚡ 请在新终端中按顺序执行以下命令进行测试：[/bold]")
        
        rprint("\n[cyan]1. 进入代码目录:[/cyan]")
        cd_command = f"cd \"{str(attempt_path.resolve())}\""
        print(cd_command)

        rprint("\n[cyan]2. 运行程序:[/cyan]")
        if env_manager == "conda":
            final_command = f"conda run -n {env_name} {ai_command}"
            print(final_command)
        elif env_manager == "venv":
            python_executable = ".venv/Scripts/python.exe" if sys.platform == "win32" else "./.venv/bin/python"
            if ai_command.startswith("python "):
                ai_command = ai_command[len("python "):]
            final_command = f"{python_executable} {ai_command}"
            print(final_command)
        else:
            print(ai_command)

        while True:
            # ... (用户选择逻辑保持不变) ...
            prompt = (
                "\n[bold]请在测试后选择下一步操作：[/bold]\n"
                "  [bold green]Y[/bold green] - 是的，程序按预期工作 (Yes)\n"
                "  [bold red]N[/bold red] - 不，程序出错了或未达预期 (No)\n"
                "  [bold blue]S[/bold blue] - 跳过此步骤 (Skip)\n"
                "  [bold magenta]A[/bold magenta] - 终止整个项目 (Abort)\n"
            )
            rprint(prompt, end="")
            choice = input("> ").strip().lower()

            if choice == 'a':
                logger.info("用户选择终止项目。")
                return "abort", None
            elif choice == 's':
                logger.info("用户选择跳过当前步骤。")
                return "skip", None
            elif choice == 'y':
                logger.info("用户确认步骤成功。")
                return "success", None
            elif choice == 'n':
                self.console.print("\n" + "="*20, style="bold red")
                self.console.print("很抱歉程序未能成功。", style="bold red")
                self.console.print("请将您在终端看到的【完整错误信息】粘贴到下方。", style="bold")
                self.console.print("如果没有错误信息，请描述【程序不符合预期的行为】。", style="bold")
                self.console.print("输入 'done' 并按回车结束。", style="bold")
                
                lines = []
                while True:
                    line = input()
                    if line.strip().lower() == 'done':
                        break
                    lines.append(line)
                
                feedback = "\n".join(lines)
                if not feedback.strip():
                    feedback = "用户报告程序执行失败，但未提供具体的错误信息或描述。"
                
                logger.info(f"获取到用户的失败反馈:\n{feedback}")
                return "failure", feedback
            else:
                rprint("[bold red]无效输入，请输入 'Y', 'N', 'S', 或 'A'。[/bold red]")
    
    def prompt_environment_cleanup_choice(self, env_name: str, env_manager: str) -> Tuple[str, Optional[str]]:
        # ... (此方法内部逻辑保持不变) ...
        self.console.print(Panel("[bold cyan]环境清理[/bold cyan]", title="🧹", title_align="left", border_style="cyan"))
        env_display_name = f"'{env_name}' ({env_manager.upper()})"
        
        prompt_lines = [
            f"项目使用的环境 [bold yellow]{env_display_name}[/bold yellow] 已创建。",
            "请选择如何操作：",
            "  [bold green]K[/bold green] - [bold]保留[/bold] (Keep) 该环境",
        ]
        
        if env_manager == 'conda':
            prompt_lines.append("  [bold blue]R[/bold blue] - [bold]重命名[/bold] (Rename) 该环境")
        
        prompt_lines.append("  [bold red]D[/bold red] - [bold]删除[/bold] (Delete) 该环境")

        prompt = "\n".join(prompt_lines)

        valid_choices = ['k', 'd']
        if env_manager == 'conda':
            valid_choices.append('r')

        while True:
            rprint(prompt)
            choice = input("> ").strip().lower()
            if choice in valid_choices:
                if choice == 'k':
                    logger.info(f"用户选择保留环境 {env_display_name}。")
                    return "keep", None
                elif choice == 'd':
                    logger.info(f"用户选择删除环境 {env_display_name}。")
                    return "delete", None
                elif choice == 'r': 
                    new_name = input("请输入新的环境名称: ").strip()
                    if new_name:
                        logger.info(f"用户选择将环境 '{env_name}' 重命名为 '{new_name}'。")
                        return "rename", new_name
                    else:
                        rprint("[bold red]新名称不能为空，请重新选择。[/bold red]")
            else:
                rprint(f"[bold red]无效输入，请输入 {'/'.join(c.upper() for c in valid_choices)}。[/bold red]")