from pathlib import Path

from alembic.command import upgrade
from alembic.config import Config
from sqlalchemy.engine import make_url

from backend.common.config import settings


def run_db_migrations() -> None:
    """启动时创建 SQLite 目录，并通过唯一初始化修订建立空库结构。"""
    # 1. 内存 SQLite 没有磁盘路径，不创建数据目录。
    url = make_url(settings.DATABASE_URL)
    if url.get_backend_name() == "sqlite" and url.database not in (
        None,
        "",
        ":memory:",
    ):
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)

    # 2. 已处于当前修订的数据库保持原样，不自动迁移历史结构。
    directory = Path(__file__).resolve().parent
    config = Config(str(directory / "alembic.ini"))
    config.set_main_option("script_location", str(directory))
    config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))
    upgrade(config, "head")
