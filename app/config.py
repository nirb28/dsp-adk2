from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )
    
    llm_provider: str = Field(default="openai")
    llm_model: str = Field(default="gpt-4")
    llm_api_key: str = Field(default="")
    llm_base_url: Optional[str] = Field(default=None)
    llm_temperature: float = Field(default=0.7)
    llm_max_tokens: int = Field(default=2000)
    
    groq_api_key: Optional[str] = Field(default=None)
    anthropic_api_key: Optional[str] = Field(default=None)
    nvidia_api_key: Optional[str] = Field(default=None)
    
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8200)
    auto_app_reload: bool = Field(default=False)
    debug_trace: bool = Field(default=False)
    
    data_dir: str = Field(default="./data")
    agents_dir: str = Field(default="./data/agents")
    tools_dir: str = Field(default="./data/tools")
    
    api_key: Optional[str] = Field(default=None)
    jwt_secret: Optional[str] = Field(default=None)
    
    log_level: str = Field(default="INFO")


settings = Settings()


os.makedirs(settings.data_dir, exist_ok=True)
os.makedirs(settings.agents_dir, exist_ok=True)
os.makedirs(settings.tools_dir, exist_ok=True)
