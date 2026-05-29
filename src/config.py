"""配置管理，基于环境变量和 pydantic-settings."""

from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    openai_api_key: str = "sk-AHTYGfbxm0klUhKw00F8A191D2F14b67Ab047dCf7dB3Ce7f"
    openai_base_url: str = "https://oneapi-comate.baidu-int.com/v1"
    llm_model: str = "gpt-5.5"
    llm_temperature: float = 0.7
    judge_model: str = "gpt-5.5"
    judge_temperature: float = 0.0
    log_level: str = "INFO"
    max_turns: int = 15

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()