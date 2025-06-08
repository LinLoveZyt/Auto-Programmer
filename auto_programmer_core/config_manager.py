# auto_programmer_core/config_manager.py
# 配置管理器模块

import configparser
import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

class ConfigManager:
    """
    配置管理器类，负责加载和提供全局配置。
    采用单例模式确保全局只有一个配置实例。
    """
    _instance = None

    def __new__(cls, config_file_path="config.ini"):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_file_path="config.ini"):
        if self._initialized:
            return
        
        load_dotenv()

        self.config = configparser.ConfigParser(interpolation=None)
        self.config_file_path = config_file_path

        if not os.path.exists(config_file_path):
            logger.error(f"配置文件 {config_file_path} 不存在。")
            raise FileNotFoundError(f"配置文件 {config_file_path} 不存在。请确保该文件位于项目根目录。")

        try:
            self.config.read(config_file_path, encoding='utf-8')
            logger.info(f"成功加载配置文件: {config_file_path}")
        except configparser.Error as e:
            logger.error(f"读取配置文件 {config_file_path} 失败: {e}")
            raise

        self.llm_provider = self.config.get("LLM", "provider", fallback="gemini")
        self.llm_api_key = os.getenv("GEMINI_API_KEY") or self.config.get("LLM", "api_key", fallback=None)
        self.llm_model_name = self.config.get("LLM", "model_name", fallback="gemini-1.5-flash-latest")
        
        if not self.llm_api_key or "YOUR_GEMINI_API_KEY" in self.llm_api_key:
            logger.warning("LLM API密钥未在环境变量 GEMINI_API_KEY 或配置文件中正确设置。")

        self.project_root_directory = self.config.get("Project", "root_directory", fallback="./workspace")
        self.prompt_template_dir = self.config.get("Project", "prompt_template_dir", fallback="./prompts")

        self.log_level = self.config.get("Logging", "level", fallback="INFO")
        self.log_file = self.config.get("Logging", "log_file", fallback=None)
        if isinstance(self.log_file, str) and not self.log_file.strip():
            self.log_file = None
        self.log_format = self.config.get("Logging", "log_format", fallback='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # --- 修改开始 ---
        self.env_manager = self.config.get("Environment", "env_manager", fallback="conda").lower()
        self.python_version = self.config.get("Environment", "python_version", fallback="3.9")
        # --- 修改结束 ---
        
        self.max_step_attempts = self.config.getint("Execution", "max_step_attempts", fallback=3)
        self.script_timeout_seconds = self.config.getint("Execution", "script_timeout_seconds", fallback=300)

        self._initialized = True
        logger.info(f"ConfigManager 初始化完成。")

    def get_llm_config(self) -> dict:
        """获取LLM相关的配置"""
        return {
            "provider": self.llm_provider,
            "api_key": self.llm_api_key,
            "model_name": self.llm_model_name
        }

    def get_project_config(self) -> dict:
        """获取项目相关的配置"""
        return {
            "root_directory": self.project_root_directory,
            "prompt_template_dir": self.prompt_template_dir
        }

    def get_logging_config(self) -> dict:
        """获取日志相关的配置"""
        return {
            "level": self.log_level,
            "log_file": self.log_file,
            "log_format": self.log_format
        }

    def get_environment_config(self) -> dict:
        """获取环境相关的配置"""
        # --- 修改开始 ---
        return {
            "env_manager": self.env_manager,
            "python_version": self.python_version
        }
        # --- 修改结束 ---
        
    def get_execution_config(self) -> dict:
        """获取执行相关的配置"""
        return {
            "max_step_attempts": self.max_step_attempts,
            "script_timeout_seconds": self.script_timeout_seconds,
        }