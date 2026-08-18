"""全局配置：读 .env 文件，提供 settings 单例。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 目录定义 —— 同款见 AIRoomBuilder/backend/app/config.py 第5-10行
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
CACHE_DIR = DATA_DIR / "vision_cache"

for _d in (DATA_DIR, UPLOAD_DIR, CACHE_DIR):
    _d.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    """同款见 AIRoomBuilder/backend/app/config.py 第16-19行：
    env_file 指定读哪个 .env；extra="ignore" 表示 .env 里多写的字段不报错。"""
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", extra="ignore", protected_namespaces=()
    )

    app_name: str = "MangaLens API"
    database_url: str = f"sqlite:///{(DATA_DIR / 'app.db').as_posix()}"

    # 大模型配置 —— 同款见 AIRoomBuilder config.py 第24-32行
    vision_provider: str = "mock"
    vision_cache_enabled: bool = True

    openai_api_key: str = ""
    openai_base_url: str = "https://apihub.agnes-ai.cn/v1"
    openai_model: str = "agnes-2.0-flash"

    def resolved_provider(self) -> str:
        """没有配置 Key 时自动回退 mock，保证项目开箱即跑。
        同款见 AIRoomBuilder/backend/app/config.py 第37-47行。"""
        p = self.vision_provider.lower().strip()
        if p == "openai" and not self.openai_api_key:
            return "mock"
        return p if p in ("mock", "openai") else "mock"

    def resolved_model(self) -> str:
        if self.resolved_provider() == "mock":
            return "mock"
        return self.openai_model


settings = Settings()
