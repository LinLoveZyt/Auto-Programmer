# auto_programmer_core/logger_setup.py
# 日志系统配置模块

import logging
import sys
from logging.handlers import RotatingFileHandler

def setup_logging(log_level_str: str, log_file: str = None, log_format: str = None):
    """
    配置全局日志系统。

    Args:
        log_level_str (str): 日志级别字符串 (e.g., "INFO", "DEBUG").
        log_file (str, optional): 日志文件路径。如果为None或空字符串，则输出到控制台。
        log_format (str, optional): 日志格式字符串。如果为None，使用默认格式。
    """
    numeric_level = getattr(logging, log_level_str.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f"无效的日志级别: {log_level_str}")

    if not log_format:
        log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    formatter = logging.Formatter(log_format)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # 清除已存在的处理器，防止重复记录
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件处理器 (如果指定了log_file)
    if log_file:
        # 使用RotatingFileHandler可以防止日志文件无限增大
        # 这里设置单个文件最大10MB，保留5个备份文件
        file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
        logging.info(f"日志将记录到文件: {log_file}")
    else:
        logging.info("日志将输出到控制台")

    logging.info(f"日志级别设置为: {log_level_str.upper()}")