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
        resolved = os.getenv(match) or env_map.get(match) or ""
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
    llm_disable_max_completion_tokens: bool = Field(default=False)
    
    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8200)
    auto_app_reload: bool = Field(default=False)
    debug_trace: bool = Field(default=False)
    ssl_verify: bool = Field(default=True)
    
    langfuse_enabled: bool = Field(default=False)
    langfuse_public_key: Optional[str] = Field(default=None)
    langfuse_secret_key: Optional[str] = Field(default=None)
    langfuse_host: Optional[str] = Field(default=None)
    
    data_dir: str = Field(default="./data")
    agents_dir: str = Field(default="./data/agents")
    tools_dir: str = Field(default="./data/tools")
    graphs_dir: str = Field(default="./data/graphs")
    sb_dir: str = Field(default="./data/sb")
    sb_metadata_dir: str = Field(default="./data/sb/metadata")
    sb_saved_analyses_dir: str = Field(default="./data/sb/analyses")
    sb_visualizations_dir: str = Field(default="./data/sb/visualizations")

    sb_host: Optional[str] = Field(default=None)
    sb_port: int = Field(default=443)
    sb_http_scheme: str = Field(default="https")
    sb_user: Optional[str] = Field(default=None)
    sb_password: Optional[str] = Field(default=None)
    sb_access_token: Optional[str] = Field(default=None)
    sb_catalog: Optional[str] = Field(default=None)
    sb_schema: Optional[str] = Field(default=None)
    sb_source: str = Field(default="dsp-adk2-ai-bi")
    sb_default_limit: int = Field(default=200)
    sb_allowed_catalogs: Optional[str] = Field(default=None)
    sb_allowed_schemas: Optional[str] = Field(default=None)
    sb_denied_columns: Optional[str] = Field(default=None)
    
    api_key: Optional[str] = Field(default=None)
    jwt_secret: Optional[str] = Field(default=None)
    
    log_level: str = Field(default="INFO")


settings = Settings()


os.makedirs(settings.data_dir, exist_ok=True)
os.makedirs(settings.agents_dir, exist_ok=True)
os.makedirs(settings.tools_dir, exist_ok=True)
os.makedirs(settings.graphs_dir, exist_ok=True)
os.makedirs(settings.sb_dir, exist_ok=True)
os.makedirs(settings.sb_metadata_dir, exist_ok=True)
os.makedirs(settings.sb_saved_analyses_dir, exist_ok=True)
os.makedirs(settings.sb_visualizations_dir, exist_ok=True)
