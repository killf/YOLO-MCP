from typing import Any, AsyncIterator
from contextlib import asynccontextmanager

import click
import uvicorn
from fastapi import FastAPI, Response
from fastapi.staticfiles import StaticFiles
from starlette.routing import Route

from backend.adapter.routers import add_router
from backend.adapter.ws import add_ws_router
from backend.middleware import add_middleware
from backend.common.logger import init_logging
from backend.common.config import settings
from backend.common.error_code import add_exception_handler
from backend.migrations.run_migrate import run_db_migrations
from backend.mcp_server import create_http_app

from .version import version as yolo_mcp_version

description = """
YOLO MCP backend.

## Users

You will be able to:

* **Signup**
* **Login**
* **Logout**.

## Projects

You will be able to:

* **CRUD**

## Project attachment

You will be able to:

* **upload attachment**
* **download attachment**
* **delete attachment**

## Project sample

You will be able to:

* **list sample**
* **create sample**
* **get sample**
* **update sample**
* **update dataset split**
"""


tags_metadata = [
    {
        "name": "users",
        "description": "Operations with users.",
    },
    {
        "name": "projects",
        "description": "Project management.",
    },
    {
        "name": "attachments",
        "description": "Project attachment management.",
    },
    {
        "name": "samples",
        "description": "Project sample management.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """初始化密钥与数据库、处理上次中断的作业，并管理 MCP 与训练生命周期。"""
    settings.initialize_secret_key()
    init_logging()
    run_db_migrations()

    from backend.application.service.auto_label import fail_interrupted_jobs
    from backend.application.service.training import fail_interrupted_runs, stop_workers

    fail_interrupted_jobs()
    fail_interrupted_runs()
    # SDK 的协议管理器每次启动独立创建，支持同一应用正常关闭后再启动。
    mcp_app = create_http_app()
    mcp_route.app = mcp_app
    async with mcp_app.router.lifespan_context(mcp_app):
        try:
            yield
        finally:
            await stop_workers()


app = FastAPI(
    lifespan=lifespan,
    title="YOLO MCP",
    description=description,
    version=yolo_mcp_version,
    terms_of_service="",
    contact={
        "name": "YOLO MCP",
        "url": "https://github.com/killf/LabelS",
    },
    license_info={
        "name": "Apache 2.0",
        "url": "https://www.apache.org/licenses/LICENSE-2.0.html",
    },
    openapi_tags=tags_metadata,
)

add_exception_handler(app=app)
add_router(app=app)
add_ws_router(app=app)
add_middleware(app=app)


class NoCacheStaticFiles(StaticFiles):
    """为 HTML 响应添加禁止缓存的头，其他静态资源沿用默认缓存行为。"""

    def file_response(self, *args: Any, **kwargs: Any) -> Response:
        resp = super().file_response(*args, **kwargs)

        # No cache for html files
        if resp.media_type == "text/html":
            resp.headers.setdefault(
                "Cache-Control", "max-age=0, no-cache, no-store, must-revalidate"
            )
            resp.headers.setdefault("Pragma", "no-cache")
            resp.headers.setdefault("Expires", "0")

        return resp


# 精确匹配 /mcp，使协议请求先于前端静态路由且无需尾斜线重定向。
mcp_route = Route("/mcp", create_http_app())
app.router.routes.append(mcp_route)
app.mount("", NoCacheStaticFiles(packages=["backend"], html=True))


@click.command()
@click.option("--host", default="localhost", help="Server host")
@click.option("--port", default=8000, help="Server port")
def cli(host: str, port: int):
    """按指定地址启动 YOLO MCP HTTP 与 WebSocket 服务。"""
    settings.PORT = port
    settings.HOST = host

    # 监听所有网卡时，显示可直接在本机浏览器打开的地址。
    browser_host = {"0.0.0.0": "127.0.0.1", "::": "::1"}.get(host, host)
    if ":" in browser_host and not browser_host.startswith("["):
        browser_host = f"[{browser_host}]"
    click.echo(f"YOLO MCP 服务地址: http://{browser_host}:{port}")

    uvicorn.run(app=app, host=settings.HOST, port=settings.PORT, ws="websockets")


if __name__ == "__main__":
    cli()
