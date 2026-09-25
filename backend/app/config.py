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
    ai_model: str = "qwen3.7-flash"

    # 待审提醒邮件:没配就不发,不影响其他功能
    smtp_host: str | None = None
    smtp_port: int = 465
    smtp_user: str | None = None
    smtp_password: str | None = None
    notify_email: str | None = None
    public_base_url: str = "https://tz5aq2zkxqhc.guyubao.com"

    wechat_appid: str | None = None
    wechat_secret: str | None = None

    model_config = {"env_prefix": "GEOGAME_"}

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p


settings = Settings()
