# auto_programmer_core/environment_manager.py
# 环境管理器模块

import logging
import subprocess
import sys
import shutil
from typing import Dict, Tuple, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class EnvironmentManager:
    """
    管理项目的虚拟环境和依赖（支持Conda和Venv）。
    """
    def __init__(self, env_config: Dict[str, str]):
        self.env_manager = env_config.get("env_manager", "conda")
        self.python_version = env_config.get("python_version")
        logger.info(f"EnvironmentManager 初始化, 使用 {self.env_manager.upper()} 管理器, 默认Python版本: {self.python_version}")

    def _get_venv_path(self, project_workspace: Path) -> Path:
        """获取venv环境的路径"""
        return project_workspace / ".venv"

    def _get_venv_python_executable(self, project_workspace: Path) -> Path:
        """获取venv环境中Python解释器的路径"""
        venv_path = self._get_venv_path(project_workspace)
        if sys.platform == "win32":
            return venv_path / "Scripts" / "python.exe"
        else:
            return venv_path / "bin" / "python"

    def _conda_env_exists(self, env_name: str) -> bool:
        """检查指定的Conda环境是否存在。"""
        logger.debug(f"检查Conda环境 '{env_name}' 是否存在...")
        try:
            result = subprocess.run(["conda", "env", "list"], capture_output=True, text=True, check=True, encoding='utf-8')
            for line in result.stdout.splitlines():
                if not line.startswith("#") and env_name in line.split():
                    env_path = line.split()[-1]
                    if Path(env_path).name == env_name:
                        logger.debug(f"发现环境 '{env_name}'。")
                        return True
            logger.debug(f"未在conda env list中发现环境 '{env_name}'。")
            return False
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.error(f"执行 `conda env list` 失败: {e}")
            if isinstance(e, FileNotFoundError):
                raise RuntimeError("Conda命令未找到。请确保Conda已安装并配置在系统PATH中。")
            return False

    def setup_project_environment(self, env_name: str, project_workspace: Path) -> bool:
        """
        根据配置的管理器，创建项目环境。
        """
        if self.env_manager == "conda":
            return self._setup_conda_environment(env_name)
        elif self.env_manager == "venv":
            return self._setup_venv_environment(project_workspace)
        else:
            logger.error(f"不支持的环境管理器: {self.env_manager}")
            return False

    def _setup_conda_environment(self, env_name: str) -> bool:
        """创建Conda虚拟环境"""
        print(f"\n[Conda] 正在检查项目环境 '{env_name}'...")
        if self._conda_env_exists(env_name):
            logger.info(f"Conda环境 '{env_name}' 已存在。")
            print(f"项目环境 '{env_name}' 已存在，跳过创建。")
            return True
        
        print(f"项目环境 '{env_name}' 不存在，正在创建...")
        logger.info(f"Conda环境 '{env_name}' 不存在，开始创建...")
        try:
            command = ["conda", "create", "-n", env_name, f"python={self.python_version}", "-y"]
            subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
            logger.info(f"成功创建Conda环境 '{env_name}'。")
            print(f"✅ 成功创建项目环境 '{env_name}'。")
            return True
        except subprocess.CalledProcessError as e:
            error_message = f"创建Conda环境 '{env_name}' 失败。\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
            logger.error(error_message)
            print(f"❌ {error_message}")
            return False
        except Exception as e:
            logger.error(f"创建Conda环境时发生未知错误: {e}", exc_info=True)
            return False

    def _setup_venv_environment(self, project_workspace: Path) -> bool:
        """创建Venv虚拟环境"""
        venv_path = self._get_venv_path(project_workspace)
        print(f"\n[Venv] 正在检查项目环境 '{venv_path}'...")
        if venv_path.exists() and (venv_path / "pyvenv.cfg").exists():
            logger.info(f"Venv环境 '{venv_path}' 已存在。")
            print(f"项目环境 '{venv_path}' 已存在，跳过创建。")
            return True

        print(f"项目环境 '{venv_path}' 不存在，正在创建...")
        logger.info(f"Venv环境 '{venv_path}' 不存在，开始创建...")
        try:
            command = [sys.executable, "-m", "venv", str(venv_path), "--clear"]
            subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
            logger.info(f"成功创建Venv环境 '{venv_path}'。")
            print(f"✅ 成功创建项目环境 '{venv_path}'。")
            return True
        except subprocess.CalledProcessError as e:
            error_message = f"创建Venv环境 '{venv_path}' 失败。\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
            logger.error(error_message)
            print(f"❌ {error_message}")
            return False
        except Exception as e:
            logger.error(f"创建Venv环境时发生未知错误: {e}", exc_info=True)
            return False

    def install_dependencies(self, project_step_path: Path, env_name: str, project_workspace: Path, dependency_filename: str) -> Tuple[bool, str, str]:
        """
        在指定环境中，根据指定的依赖文件安装依赖。
        """
        if not dependency_filename:
            logger.info("未指定依赖文件名，跳过依赖安装。")
            return True, "No dependency file specified.", ""
            
        requirements_file = project_step_path / dependency_filename
        if not requirements_file.exists() or requirements_file.stat().st_size == 0:
            logger.info(f"未找到或空的依赖文件 '{dependency_filename}', 跳过依赖安装。")
            return True, f"Dependency file '{dependency_filename}' not found or is empty.", ""

        if self.env_manager == "conda":
            print(f"[Conda] 在环境 '{env_name}' 中通过 '{dependency_filename}' 安装依赖...")
            command = ["conda", "run", "-n", env_name, "pip", "install", "-r", str(requirements_file)]
        elif self.env_manager == "venv":
            venv_python = self._get_venv_python_executable(project_workspace)
            print(f"[Venv] 在环境 '{project_workspace.name}' 中通过 '{dependency_filename}' 安装依赖...")
            command = [str(venv_python), "-m", "pip", "install", "-r", str(requirements_file)]
        else:
            return False, "", "不支持的环境管理器"

        logger.info(f"开始在环境 '{env_name or project_workspace.name}' 中使用 '{dependency_filename}' 安装依赖...")
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
            logger.info(f"成功安装依赖: \n{result.stdout}")
            print(f"✅ 依赖安装成功。")
            return True, result.stdout, result.stderr
        except subprocess.CalledProcessError as e:
            error_message = f"依赖安装失败。\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
            logger.error(error_message)
            print(f"❌ {error_message}")
            return False, e.stdout, e.stderr

    def delete_environment(self, env_name: str, project_workspace: Path) -> bool:
        """删除指定的虚拟环境。"""
        if self.env_manager == "conda":
            print(f"[Conda] 正在删除环境 '{env_name}'...")
            logger.info(f"开始删除Conda环境 '{env_name}'...")
            try:
                command = ["conda", "env", "remove", "--name", env_name, "-y"]
                result = subprocess.run(command, capture_output=True, text=True, check=True, encoding='utf-8')
                logger.info(f"成功删除Conda环境 '{env_name}':\n{result.stdout}")
                print(f"✅ 成功删除环境 '{env_name}'。")
                return True
            except subprocess.CalledProcessError as e:
                error_message = f"删除Conda环境 '{env_name}' 失败。\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
                logger.error(error_message)
                print(f"❌ {error_message}")
                return False
        elif self.env_manager == "venv":
            venv_path = self._get_venv_path(project_workspace)
            print(f"[Venv] 正在删除环境 '{venv_path}'...")
            logger.info(f"开始删除Venv环境 '{venv_path}'...")
            try:
                shutil.rmtree(venv_path)
                logger.info(f"成功删除Venv环境 '{venv_path}'。")
                print(f"✅ 成功删除环境 '{venv_path}'。")
                return True
            except OSError as e:
                error_message = f"删除Venv环境 '{venv_path}' 失败: {e}"
                logger.error(error_message)
                print(f"❌ {error_message}")
                return False
        return False

    def rename_environment(self, old_name: str, new_name: str, project_workspace: Path) -> bool:
        """重命名虚拟环境。注意：Venv不支持重命名。"""
        if self.env_manager == "conda":
            print(f"[Conda] 正在将环境 '{old_name}' 重命名为 '{new_name}'...")
            logger.info(f"开始重命名Conda环境 '{old_name}' -> '{new_name}'...")
            
            print(f"正在克隆 '{old_name}' 到 '{new_name}'...")
            logger.info(f"克隆环境 '{old_name}' 到 '{new_name}'。")
            try:
                command_clone = ["conda", "create", "--name", new_name, "--clone", old_name, "-y"]
                subprocess.run(command_clone, capture_output=True, text=True, check=True, encoding='utf-8')
                logger.info(f"成功克隆环境到 '{new_name}'。")
                print(f"✅ 克隆成功。")
            except subprocess.CalledProcessError as e:
                error_message = f"克隆Conda环境 '{old_name}' 失败。\nSTDOUT: {e.stdout}\nSTDERR: {e.stderr}"
                logger.error(error_message)
                print(f"❌ {error_message}")
                return False

            logger.info(f"准备删除旧环境 '{old_name}'。")
            return self.delete_environment(old_name, project_workspace)
        elif self.env_manager == "venv":
            logger.warning("Venv 环境直接与项目文件夹绑定，不支持重命名操作。")
            print("⚠️ Venv 环境不支持重命名。")
            return False
        return False