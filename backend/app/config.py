from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_url: str = "sqlite+aiosqlite:///./geogame.db"
    jwt_secret: str = "dev-secret-change-in-prod"
    jwt_expire_hours: int = 24 * 30
    admin_token: str = "dev-admin"
    upload_dir: str = "./uploads"
    fake_ai: bool = True

    oss_access_key_id: str | None = None
    oss_access_key_secret: str | None = None
    oss_bucket: str | None = None
    oss_endpoint: str | None = None  # e.g. https://oss-cn-beijing.aliyuncs.com

    ai_api_key: str | None = None
    ai_base_url: str | None = None  # OpenAI 兼容地址,不带尾部斜杠
    ai_model: str = "qwen3-vl-plus"

    wechat_appid: str | None = None
    wechat_secret: str | None = None

    model_config = {"env_prefix": "GEOGAME_"}

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
