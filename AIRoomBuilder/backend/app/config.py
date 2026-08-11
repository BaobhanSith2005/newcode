from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = BACKEND_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
CACHE_DIR = DATA_DIR / "vision_cache"
MODELS_DIR = PROJECT_ROOT / "models"

for _d in (DATA_DIR, UPLOAD_DIR, CACHE_DIR, MODELS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", extra="ignore", protected_namespaces=()
    )

    app_name: str = "AI Room Builder API"
    database_url: str = f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"

    vision_provider: str = "mock"
    vision_cache_enabled: bool = True

    dashscope_api_key: str = ""
    dashscope_model: str = "qwen-vl-max-latest"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    def resolved_provider(self) -> str:
        """没有配置对应 Key 时自动回退到 mock，保证项目开箱即跑。"""
        p = self.vision_provider.lower().strip()
        key_map = {
            "dashscope": self.dashscope_api_key,
            "openai": self.openai_api_key,
            "gemini": self.gemini_api_key,
        }
        if p in key_map and not key_map[p]:
            return "mock"
        return p if p in ("mock", "dashscope", "openai", "gemini") else "mock"

    def resolved_model(self) -> str:
        """返回实际生效的视觉模型名（mock 时返回 'mock'）。"""
        model_map = {
            "dashscope": self.dashscope_model,
            "openai": self.openai_model,
            "gemini": self.gemini_model,
        }
        return model_map.get(self.resolved_provider(), "mock")


settings = Settings()
