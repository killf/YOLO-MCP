import secrets
from pathlib import Path

from loguru import logger
from pydantic import Field, PrivateAttr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="YOLO_MCP_",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    HOST: str = "localhost"
    PORT: int = 8000
    API_V1_STR: str = "/api/v1"

    # SQLite 的持久化目录；图片、模型和训练日志均保存在该本地目录下。
    DATA_DIR: Path = Field(default_factory=lambda: Path.home() / ".yolo-mcp")
    UPLOAD_FILE_MAX_SIZE: int = 200_000_000  # ~200MB
    THUMBNAIL_HEIGH_PIXEL: int = 120

    USE_AUTO_LABEL: bool = True
    DEVICE: str = ""  # 留空自动选择 CUDA/ROCm、MPS 或 CPU。

    # 远程部署时显式填写实际域名，保留 MCP 的 Host/Origin 校验。
    MCP_ALLOWED_HOSTS: list[str] = [
        "127.0.0.1",
        "localhost",
        "[::1]",
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
    ]
    MCP_ALLOWED_ORIGINS: list[str] = [
        "http://127.0.0.1",
        "http://localhost",
        "http://[::1]",
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    ]

    # SQLite 默认与本地项目文件使用同一根目录。
    DATABASE_URL: str = Field(
        default="",
        description="Database connection URL. Supports SQLite and MySQL.",
    )

    _secret_key: str = PrivateAttr(default="")

    TOKEN_GENERATE_ALGORITHM: str = "HS256"
    TOKEN_ACCESS_EXPIRE_MINUTES: int = 30
    # Sliding refresh: when an authenticated request arrives with a token whose
    # remaining lifetime is below this many minutes, a freshly issued token is
    # returned via the `X-New-Token` response header so active users never get
    # logged out. Should be smaller than TOKEN_ACCESS_EXPIRE_MINUTES.
    TOKEN_REFRESH_THRESHOLD_MINUTES: int = 15
    TOKEN_TYPE: str = "Bearer"
    EXPOSE_INTERNAL_ERRORS: bool = False

    @model_validator(mode="after")
    def default_database_directory(self) -> "Settings":
        """未指定数据库地址时，将 SQLite 放到配置后的本地数据根目录。"""
        self.DATA_DIR = self.DATA_DIR.expanduser().resolve()
        if not self.DATABASE_URL:
            directory = self.DATA_DIR.as_posix().rstrip("/")
            self.DATABASE_URL = f"sqlite:///{directory}/labels.sqlite"
        return self

    def initialize_secret_key(self) -> None:
        """应用启动时创建或读取持久签名密钥；无效文件直接报错，不覆盖原值。"""
        self.DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = self.DATA_DIR / "secret.key"
        try:
            with path.open("x", encoding="utf-8") as stream:
                key = secrets.token_hex(32)
                stream.write(key)
        except FileExistsError:
            key = path.read_text(encoding="utf-8").strip()
        if len(key) != 64 or any(char not in "0123456789abcdef" for char in key):
            raise ValueError("数据目录中的 secret.key 无效，无法启动签名服务")
        self._secret_key = key

    @property
    def secret_key(self) -> str:
        """返回启动时加载的签名密钥，禁止在初始化前签发令牌或图片地址。"""
        if not self._secret_key:
            raise RuntimeError("签名密钥尚未初始化，请先启动应用")
        return self._secret_key


settings = Settings()
logger.info("Data directory: {}", settings.DATA_DIR)
