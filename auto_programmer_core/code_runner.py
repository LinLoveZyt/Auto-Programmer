# auto_programmer_core/code_runner.py
# 代码执行器模块

import logging
import subprocess
from pathlib import Path
from typing import Tuple, Dict, List
import sys
import tempfile
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

# --- 策略接口定义 ---

class ExecutionStrategy(ABC):
    """
    执行策略的抽象基类。
    """
    @abstractmethod
    def execute(self,
                python_args: List[str], # 修改: 从 script_path 改为 python_args
                cwd: Path,
                timeout: int,
                env_manager: str,
                env_name: str,
                project_workspace: Path
               ) -> Tuple[str, str, int]:
        """
        执行Python命令。
        """
        pass

# --- 具体策略实现 ---

class AutomatedExecutionStrategy(ExecutionStrategy):
    """
    在类Unix和Windows系统上，使用subprocess自动执行脚本的统一策略。
    """
    def _get_venv_python_executable(self, project_workspace: Path) -> Path:
        """获取venv环境中Python解释器的路径"""
        venv_path = project_workspace / ".venv"
        if sys.platform == "win32":
            return venv_path / "Scripts" / "python.exe"
        else:
            return venv_path / "bin" / "python"

    def execute(self,
                python_args: List[str], # 修改: 接收通用参数
                cwd: Path,
                timeout: int,
                env_manager: str,
                env_name: str,
                project_workspace: Path
               ) -> Tuple[str, str, int]:
        
        command = []
        
        if env_manager == "conda":
            # 修改: 构建通用conda命令
            command = ["conda", "run", "-n", env_name, "python"] + python_args
        elif env_manager == "venv":
            python_executable = self._get_venv_python_executable(project_workspace)
            if not python_executable.exists():
                err_msg = f"Venv Python解释器未找到: {python_executable}"
                logger.error(err_msg)
                return "", err_msg, -1
            # 修改: 构建通用venv命令
            command = [str(python_executable)] + python_args
        else:
            err_msg = f"不支持的环境管理器: {env_manager}"
            logger.error(err_msg)
            return "", err_msg, -1

        try:
            # (原有逻辑保持不变, 此处省略以保持简洁)
            if sys.platform == "win32":
                print("将在【新的终端窗口】中运行脚本 (仅限Windows)...")
                print("⚙️ 正在编译和执行代码，请查看弹出的新窗口...")
                
                process = subprocess.Popen(
                    command,
                    cwd=str(cwd),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    creationflags=subprocess.CREATE_NEW_CONSOLE
                )
                
                try:
                    stdout, stderr = process.communicate(timeout=timeout)
                    return stdout, stderr, process.returncode
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                    timeout_msg = f"脚本执行超时（超过 {timeout} 秒），已强制终止。"
                    logger.error(timeout_msg, exc_info=True)
                    print(f"\n❌ {timeout_msg}")
                    full_stderr = (stderr or "") + "\n" + timeout_msg
                    return stdout or "", full_stderr, -1
            else:
                print("将在【当前终端会话】中运行脚本 (macOS/Linux)...")
                print("⚙️ 正在编译和执行代码，这可能需要一点时间...")
                
                result = subprocess.run(
                    command,
                    cwd=str(cwd),
                    capture_output=True,
                    text=True,
                    encoding='utf-8',
                    timeout=timeout
                )
                
                return result.stdout, result.stderr, result.returncode
        
        except subprocess.TimeoutExpired:
            timeout_msg = f"脚本执行超时（超过 {timeout} 秒），已强制终止。"
            logger.error(timeout_msg, exc_info=True)
            print(f"\n❌ {timeout_msg}")
            return "", timeout_msg, -1
        except Exception as e:
            logger.error(f"执行脚本时发生非预期的子进程错误: {e}", exc_info=True)
            return "", str(e), -1

# --- 代码执行器上下文 ---

class CodeRunner:
    """
    在指定的虚拟环境中执行Python脚本、模块或测试，并捕获输出。
    """

    def __init__(self, timeout: int, env_config: Dict[str, str]):
        """
        初始化CodeRunner。
        """
        self.timeout = timeout
        self.env_manager = env_config.get("env_manager", "conda")
        self.strategy: ExecutionStrategy = AutomatedExecutionStrategy()
        logger.info(f"CodeRunner 初始化，使用自动化执行策略。超时: {self.timeout}s。")

    def _execute(self, python_args: List[str], env_name: str, cwd: Path, project_workspace: Path) -> Tuple[str, str, int]:
        """
        通用的执行方法。
        """
        abs_cwd = cwd.resolve()
        logger.info(f"准备在环境 '{env_name}' 中执行命令: python {' '.join(python_args)}, 工作目录: {abs_cwd}")
        
        try:
            stdout, stderr, return_code = self.strategy.execute(
                python_args=python_args,
                cwd=abs_cwd,
                timeout=self.timeout,
                env_manager=self.env_manager,
                env_name=env_name,
                project_workspace=project_workspace
            )

            print(f"命令执行评估信息已收集。")
            logger.info(f"命令执行完毕。返回码: {return_code}")
            if stdout: logger.debug(f"STDOUT:\n{stdout}")
            if stderr: logger.warning(f"STDERR:\n{stderr}")

            return stdout, stderr, return_code
            
        except Exception as e:
            logger.error(f"执行命令时发生严重错误: {e}", exc_info=True)
            return "", str(e), -1

    def run_script(self, script_path: Path, env_name: str, cwd: Path, project_workspace: Path) -> Tuple[str, str, int]:
        """
        执行指定的Python脚本。
        """
        abs_script_path = script_path.resolve()
        abs_cwd = cwd.resolve()

        if not abs_script_path.exists():
            error_msg = f"要执行的脚本 '{abs_script_path}' 不存在。"
            logger.error(error_msg)
            return "", error_msg, -1
        
        try:
            relative_script_path = abs_script_path.relative_to(abs_cwd)
        except ValueError:
            error_msg = f"脚本路径 '{abs_script_path}' 不在工作目录 '{abs_cwd}' 中。"
            logger.error(error_msg)
            return "", error_msg, -1

        print(f"\n在环境 '{env_name}' (使用 {self.env_manager.upper()}) 中执行脚本: {relative_script_path}...")
        return self._execute([str(relative_script_path)], env_name, cwd, project_workspace)

    def run_tests(self, test_paths: List[str], env_name: str, cwd: Path, project_workspace: Path) -> Tuple[str, str, int]:
        """
        使用 pytest 运行指定的测试。
        """
        print(f"\n🤖 在环境 '{env_name}' (使用 {self.env_manager.upper()}) 中运行自动化测试...")
        
        # 确保测试路径存在
        for test_path_str in test_paths:
            if not (cwd / test_path_str).exists():
                error_msg = f"要测试的路径 '{test_path_str}' 在工作目录 '{cwd}' 中不存在。"
                logger.error(error_msg)
                return "", error_msg, -1

        # 构建 pytest 命令
        python_args = ["-m", "pytest"] + test_paths
        
        return self._execute(python_args, env_name, cwd, project_workspace)
