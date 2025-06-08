# auto_programmer_core/llm_interface.py
# LLM接口模块

import logging
import json
import re
from abc import ABC, abstractmethod
from typing import Dict, Any, Union
import time
import random

# 尝试导入 google.genai
try:
    from google import genai as user_specific_google_genai_sdk
    from google.genai import errors as genai_errors
    logging.getLogger(__name__).info("成功导入 'google.genai' 及其错误处理模块。")
except ImportError:
    logging.getLogger(__name__).critical("关键错误：无法从 'google' 导入 'genai'。请确保相关Google AI库已安装。")
    user_specific_google_genai_sdk = None
    genai_errors = None

logger = logging.getLogger(__name__)

class AbstractLLMProvider(ABC):
    """
    LLM提供者的抽象基类，定义了所有提供者必须实现的接口。
    """
    @abstractmethod
    def generate_response(self, prompt_text: str, **kwargs) -> str:
        """
        向LLM发送Prompt并获取纯文本回复。
        """
        pass

class GeminiProvider(AbstractLLMProvider):
    """
    使用Google Gemini API的LLM提供者实现。
    """
    def __init__(self, api_key: str, model_name: str, max_retries: int = 3):
        if not api_key:
            raise ValueError("Gemini API密钥不能为空。")
        self.model_name = model_name
        self.max_retries = max_retries
        if user_specific_google_genai_sdk is None or genai_errors is None:
            raise ImportError("由于 'google.genai' SDK未能导入, 无法初始化GeminiProvider。")
        try:
            self.client = user_specific_google_genai_sdk.Client(api_key=api_key)
            logger.info(f"GeminiProvider 初始化成功。配置模型: {self.model_name}")
        except Exception as e:
            raise ConnectionError(f"创建 'google.genai.Client' 实例时发生错误: {e}") from e

    def generate_response(self, prompt_text: str, **kwargs) -> str:
        last_exception = None
        for attempt in range(self.max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name, 
                    contents=prompt_text
                )
                if hasattr(response, 'text') and response.text:
                    logger.info("成功从Gemini获取回复。")
                    return response.text
                else:
                    last_exception = RuntimeError("Gemini API 未返回有效的文本内容。")
                    time.sleep(5)
                    continue
            except genai_errors.ResourceExhaustedError as e:
                last_exception = e
                wait_time = (2 ** attempt) * 15 + random.uniform(0, 1)
                logger.warning(f"触发API速率限制 (429)。第 {attempt + 1}/{self.max_retries} 次尝试。将在 {wait_time:.2f} 秒后重试。")
                print(f"⚠️  检测到API请求过于频繁，系统将自动在 {int(wait_time)} 秒后重试...")
                time.sleep(wait_time)
                continue
            except Exception as e:
                logger.error(f"与Gemini API 交互时发生错误: {e}")
                raise RuntimeError(f"Gemini API 调用失败: {e}") from e
        raise RuntimeError(f"Gemini API 调用在 {self.max_retries} 次重试后最终失败: {last_exception}") from last_exception


class LLMInterface:
    """
    LLM接口类，作为与LLM提供者交互的统一入口，并增加了响应处理能力。
    """
    def __init__(self, llm_config: dict):
        self.provider_type = llm_config.get("provider", "gemini").lower()
        self.provider_config = llm_config
        self.provider: AbstractLLMProvider = self._create_provider()
        logger.info(f"LLMInterface 初始化完成，使用 {self.provider_type} 提供者。")

    def _create_provider(self) -> AbstractLLMProvider:
        if self.provider_type == "gemini":
            api_key = self.provider_config.get("api_key")
            model_name = self.provider_config.get("model_name")
            if not api_key or not model_name:
                raise ValueError("Gemini API密钥和模型名称必须在配置中提供。")
            return GeminiProvider(api_key=api_key, model_name=model_name)
        else:
            raise ValueError(f"不支持的LLM提供者类型: {self.provider_type}")
    
    def _clean_json_response(self, text: str) -> str:
        """
        【已重构】清理LLM返回的可能包含Markdown标记或格式错误的JSON字符串。
        此函数现在可以处理字符串字面量中未转义的换行符，这是导致解析失败的主要原因。
        """
        # 1. 移除Markdown代码块标记
        match = re.search(r"```(json)?\s*([\s\S]*?)\s*```", text, re.DOTALL)
        if match:
            content = match.group(2).strip()
        else:
            content = text.strip()

        # 2. 修正核心问题：处理字符串字面量中未转义的特殊字符
        # 这是一个更健壮的方法，它会遍历字符串，跟踪是否在字符串字面量内部，
        # 并且只在内部时转义换行符等特殊字符。
        escaped_content = []
        in_string = False
        is_escaped = False

        for char in content:
            # 如果前一个字符是转义符 '\'，则当前字符不作为特殊字符处理
            if is_escaped:
                escaped_content.append(char)
                is_escaped = False
                continue

            # 遇到转义符
            if char == '\\':
                is_escaped = True
                escaped_content.append(char)
                continue

            # 遇到双引号，切换 "在字符串内/外" 的状态
            if char == '"':
                in_string = not in_string

            # 核心逻辑：如果在字符串内部且遇到换行符或制表符，则进行转义
            if in_string and char == '\n':
                escaped_content.append('\\n')
            elif in_string and char == '\t':
                escaped_content.append('\\t')
            else:
                escaped_content.append(char)
        
        return "".join(escaped_content)

    def generate_response(self, prompt: str, expect_json: bool = False, **kwargs) -> Union[str, Dict[str, Any]]:
        """
        通过已配置的LLM提供者发送Prompt并获取回复。
        如果 expect_json 为 True，则尝试将回复解析为JSON字典。
        """
        logger.info(f"LLMInterface 准备向 {self.provider_type} 提供者发送Prompt。期望JSON: {expect_json}")
        print("🤖 正在与AI进行深度沟通，这可能需要一点时间，请稍候...")
        try:
            raw_response = self.provider.generate_response(prompt_text=prompt, **kwargs)

            if not expect_json:
                return raw_response
            
            cleaned_response = self._clean_json_response(raw_response)
            try:
                json_data = json.loads(cleaned_response)
                logger.info("成功将LLM的回复解析为JSON。")
                return json_data
            except json.JSONDecodeError as e:
                logger.error(f"解析LLM响应为JSON失败: {e}. 原始回复(清理后): '{cleaned_response}'")
                return {
                    "error": "json_decode_error",
                    "message": str(e),
                    "original_response": raw_response
                }

        except Exception as e:
            logger.error(f"LLMInterface 在调用 provider.generate_response 时捕获到错误: {e}")
            print(f"❌ 在与AI沟通时发生错误: {e}")
            raise