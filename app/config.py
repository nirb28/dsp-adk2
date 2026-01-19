from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional, Dict
import os
import re
from dotenv import dotenv_values


def _expand_env_value(value: str, env_map: Dict[str, str]) -> str:
    pattern = r"\$\{([^}]+)\}"
    result = value
    for match in re.findall(pattern, value):
        resolved = env_map.get(match) or os.getenv(match) or ""
        result = result.replace(f"${{{match}}}", resolved)
    return result


def _load_env_with_expansion(path: str = ".env") -> None:
    raw_values = dotenv_values(path)
    resolved = {k: ("" if v is None else str(v)) for k, v in raw_values.items()}

    for _ in range(3):
        updated = False
        for key, value in resolved.items():
            expanded = _expand_env_value(value, {**resolved, **os.environ})
            if expanded != value:
                resolved[key] = expanded
                updated = True
        if not updated:
            break

    for key, value in resolved.items():
        os.environ.setdefault(key, value)


_load_env_with_expansion()


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
    
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8200)
    auto_app_reload: bool = Field(default=False)
    debug_trace: bool = Field(default=False)
    
    data_dir: str = Field(default="./data")
    agents_dir: str = Field(default="./data/agents")
    tools_dir: str = Field(default="./data/tools")
    graphs_dir: str = Field(default="./data/graphs")
    
    api_key: Optional[str] = Field(default=None)
    jwt_secret: Optional[str] = Field(default=None)
    
    log_level: str = Field(default="INFO")


settings = Settings()


os.makedirs(settings.data_dir, exist_ok=True)
os.makedirs(settings.agents_dir, exist_ok=True)
os.makedirs(settings.tools_dir, exist_ok=True)
os.makedirs(settings.graphs_dir, exist_ok=True)
