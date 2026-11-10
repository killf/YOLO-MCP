"""使用个人访问令牌提供 Streamable HTTP MCP，复用同一套项目业务与权限。"""

import base64
import binascii
import json
from contextlib import contextmanager
from io import BytesIO

from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from starlette.middleware.authentication import AuthenticationMiddleware
from mcp.server import MCPServer
from mcp.server.auth.middleware.auth_context import (
    AuthContextMiddleware,
    get_access_token,
)
from mcp.server.auth.middleware.bearer_auth import (
    BearerAuthBackend,
    RequireAuthMiddleware,
)
from mcp.server.auth.provider import AccessToken
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations

from backend.application.command.attachment import (
    AttachmentCommand,
    AttachmentDeleteCommand,
)
from backend.application.command.project import BasicConfigCommand, UpdateCommand
from backend.application.command.sample import CreateSampleCommand, PatchSampleCommand
from backend.application.command.training import StartTrainingCommand
from backend.application.service import (
    access_token,
    attachment,
    auto_label,
    project,
    sample,
    training,
)
from backend.common.config import settings
from backend.common.db import SessionLocal
from backend.domain.models.sample import DatasetSplit
from backend.version import version


class PersonalTokenVerifier:
    """将有效个人令牌转换成 SDK 身份，不接受网页登录 JWT。"""

    async def verify_token(self, token: str) -> AccessToken | None:
        """校验摘要和账号状态；无效令牌返回 None，不向 SDK 暴露数据库对象。"""
        if not token.startswith("ymcp_"):
            return None
        try:
            with SessionLocal() as db:
                user = access_token.authenticate(db, token, record_usage=False)
                return AccessToken(
                    token=token,
                    client_id="yolo-mcp-pat",
                    subject=str(user.id),
                    scopes=["projects"],
                )
        except HTTPException:
            return None


verifier = PersonalTokenVerifier()
server = MCPServer(
    "YOLO MCP",
    version=version,
    instructions="先查询项目配置和类别，再上传、标注或训练。所有工具继承令牌所属用户的当前项目权限；删除仅限拥有者或系统管理员。",
)
read_only = ToolAnnotations(readOnlyHint=True, destructiveHint=False)
write = ToolAnnotations(readOnlyHint=False, destructiveHint=False)
destructive = ToolAnnotations(readOnlyHint=False, destructiveHint=True)


@contextmanager
def authorized_session():
    """为一次工具调用打开数据库，并重新验证令牌；不复用用户或权限快照。"""
    auth = get_access_token()
    if auth is None:
        raise ToolError("缺少个人访问令牌")
    with SessionLocal() as db:
        try:
            user = access_token.authenticate(db, auth.token)
            yield db, user
        except HTTPException as error:
            raise ToolError(f"{error.status_code}: {error.detail}") from None
        except (ValidationError, ValueError) as error:
            raise ToolError(str(error)) from None


@server.tool(annotations=read_only)
async def list_projects(page: int = 0, size: int = 20) -> dict:
    """分页查询有权访问的项目。page 从 0 开始，size 为 1 至 100。"""
    if page < 0 or not 1 <= size <= 100:
        raise ToolError("分页参数无效")
    with authorized_session() as (db, user):
        rows, total = await project.list_by(db, user, page, size)
        return {"data": [row.model_dump(mode="json") for row in rows], "total": total}


@server.tool(annotations=read_only)
async def get_project(project_id: int) -> dict:
    """读取项目的标注类别、模型设置、训练默认参数和统计。"""
    with authorized_session() as (db, user):
        return (await project.get(db, project_id, user)).model_dump(mode="json")


@server.tool(annotations=write)
async def create_project(name: str, description: str = "", tips: str = "") -> dict:
    """创建当前用户拥有的图片项目；后续通过 update_project 设置标注类别。"""
    with authorized_session() as (db, user):
        command = BasicConfigCommand(
            name=name, description=description, tips=tips, media_type="IMAGE"
        )
        return (await project.create(db, command, user)).model_dump(mode="json")


@server.tool(annotations=write)
async def update_project(project_id: int, changes: UpdateCommand) -> dict:
    """更新项目配置，仅拥有者或系统管理员可用；config 是标注配置的 JSON 字符串。"""
    with authorized_session() as (db, user):
        return (await project.update(db, project_id, changes, user)).model_dump(
            mode="json"
        )


@server.tool(annotations=destructive)
async def delete_project(project_id: int) -> dict:
    """删除项目，仅拥有者或系统管理员可用。"""
    with authorized_session() as (db, user):
        return (await project.delete(db, project_id, user)).model_dump()


@server.tool(annotations=read_only)
async def list_samples(
    project_id: int, page: int = 0, size: int = 20, split: DatasetSplit | None = None
) -> dict:
    """查询项目图片和标注，可按 train/test 筛选；page 从 0 开始。"""
    if page < 0 or not 1 <= size <= 100:
        raise ToolError("分页参数无效")
    with authorized_session() as (db, user):
        rows, total = await sample.list_by(
            db, project_id, None, None, page, size, None, user, split
        )
        return {"data": [row.model_dump(mode="json") for row in rows], "total": total}


@server.tool(annotations=read_only)
async def get_sample(project_id: int, sample_id: int) -> dict:
    """读取图片预览地址和可编辑的人工标注。"""
    with authorized_session() as (db, user):
        return (await sample.get(db, project_id, sample_id, user)).model_dump(
            mode="json"
        )


@server.tool(annotations=write)
async def upload_image(
    project_id: int,
    filename: str,
    image_base64: str,
    split: DatasetSplit = DatasetSplit.TRAIN,
) -> dict:
    """上传一张 Base64 编码图片并创建样本；不接受服务器文件路径或外部 URL。"""
    try:
        content = base64.b64decode(image_base64, validate=True)
    except (binascii.Error, ValueError):
        raise ToolError("图片必须是有效的 Base64 编码") from None
    if len(content) > settings.UPLOAD_FILE_MAX_SIZE:
        raise ToolError("图片超过上传大小限制")
    with authorized_session() as (db, user):
        upload = UploadFile(filename=filename, file=BytesIO(content))
        file = None
        try:
            file = await attachment.create(
                db, project_id, AttachmentCommand(file=upload), user
            )
            created = await sample.create(
                db,
                project_id,
                [CreateSampleCommand(file_id=file.id, split=split)],
                user,
            )
        except Exception:
            if file is not None:
                await attachment.delete(
                    db,
                    project_id,
                    AttachmentDeleteCommand(attachment_ids=[file.id]),
                    user,
                )
            raise
        finally:
            await upload.close()
        return {"sample_id": created.ids[0], "file": file.model_dump(mode="json")}


@server.tool(annotations=write)
async def save_annotation(
    project_id: int, sample_id: int, result: dict, annotated_count: int
) -> dict:
    """保存并确认标注。result 使用 rectTool.result 框数组，可包含 rotate；坐标为像素。"""
    if annotated_count < 0:
        raise ToolError("标注数量不能小于 0")
    with authorized_session() as (db, user):
        command = PatchSampleCommand(
            data={"result": json.dumps(result)}, annotated_count=annotated_count
        )
        return (
            await sample.patch(db, project_id, sample_id, command, user)
        ).model_dump(mode="json")


@server.tool(annotations=write)
async def set_sample_split(
    project_id: int, sample_id: int, split: DatasetSplit
) -> dict:
    """调整训练集或测试集，不修改已有标注。"""
    with authorized_session() as (db, user):
        return (
            await sample.patch(
                db, project_id, sample_id, PatchSampleCommand(split=split), user
            )
        ).model_dump(mode="json")


@server.tool(annotations=destructive)
async def delete_samples(project_id: int, sample_ids: list[int]) -> dict:
    """删除指定项目的样本和原图，仅拥有者或系统管理员可用。"""
    with authorized_session() as (db, user):
        if not sample_ids:
            raise ToolError("请提供要删除的样本 ID")
        return (await sample.delete(db, project_id, sample_ids, user)).model_dump()


@server.tool(annotations=write)
async def auto_label_image(project_id: int, sample_id: int) -> dict:
    """使用项目配置的算法和权重生成候选框，不自动确认人工标注。"""
    with authorized_session() as (db, user):
        return (await auto_label.create(db, project_id, sample_id, user)).model_dump(
            mode="json"
        )


@server.tool(annotations=write)
async def start_auto_label(project_id: int) -> dict:
    """为项目待标注图片创建 AI 批次，返回批次 ID 和进度。"""
    with authorized_session() as (db, user):
        return (await auto_label.create_batch_job(db, project_id, user)).model_dump(
            mode="json"
        )


@server.tool(annotations=read_only)
async def get_auto_label_status(project_id: int, job_id: int) -> dict:
    """读取 AI 批次状态与完成数量。"""
    with authorized_session() as (db, user):
        return auto_label.get_batch_job(db, project_id, job_id, user).model_dump(
            mode="json"
        )


@server.tool(annotations=write)
async def start_training(project_id: int, parameters: StartTrainingCommand) -> dict:
    """启动一次异步 YOLO26 训练；未指定字段使用项目默认参数，返回记录 ID。"""
    with authorized_session() as (db, user):
        return (await training.start(db, project_id, parameters, user)).model_dump(
            mode="json"
        )


@server.tool(annotations=read_only)
async def list_training_runs(project_id: int, page: int = 0, size: int = 20) -> dict:
    """分页读取训练记录，包含状态、实际参数、指标和模型名称。"""
    if page < 0 or not 1 <= size <= 100:
        raise ToolError("分页参数无效")
    with authorized_session() as (db, user):
        rows, total = training.list_runs(db, project_id, user, page, size)
        return {"data": [row.model_dump(mode="json") for row in rows], "total": total}


@server.tool(annotations=read_only)
async def get_training_run(project_id: int, run_id: int) -> dict:
    """查询指定训练的状态、参数、指标及产出权重。"""
    with authorized_session() as (db, user):
        return training.get_run(db, project_id, run_id, user).model_dump(mode="json")


@server.tool(annotations=read_only)
async def get_training_log(project_id: int, run_id: int) -> dict:
    """读取训练日志末尾，最多 64 KiB。"""
    with authorized_session() as (db, user):
        return {"log": training.get_log(db, project_id, run_id, user)}


@server.tool(annotations=read_only)
async def list_models(project_id: int, algorithm: str = "yolo") -> dict:
    """列出项目权重或所选标注算法的官方模型 ID。"""
    with authorized_session() as (db, user):
        return {"models": auto_label.list_models(db, project_id, user, algorithm)}


@server.tool(annotations=read_only)
async def get_model_download(project_id: int, model_name: str) -> dict:
    """返回模型大小和下载接口路径；下载请求需携带当前 Bearer 令牌。"""
    with authorized_session() as (db, user):
        file = training.model_file(db, project_id, model_name, user)
        return {
            "name": file.name,
            "size": file.stat().st_size,
            "path": f"{settings.API_V1_STR}/projects/{project_id}/models/{file.name}",
        }


@server.tool(annotations=destructive)
async def clear_training_log(project_id: int, run_id: int) -> dict:
    """清理本次运行目录及数据快照，保留记录和模型；仅拥有者或管理员可用。"""
    with authorized_session() as (db, user):
        training.clear_logs(db, project_id, run_id, user)
        return {"ok": True}


@server.tool(annotations=destructive)
async def delete_training_run(project_id: int, run_id: int) -> dict:
    """删除终态训练记录及其模型、日志；仅拥有者或系统管理员可用。"""
    with authorized_session() as (db, user):
        training.delete_run(db, project_id, run_id, user)
        return {"ok": True}


def create_http_app():
    """每次应用启动使用独立协议生命周期，手动 PAT 模式不提供 OAuth 流程。"""
    app = server.streamable_http_app(
        json_response=True,
        stateless_http=True,
        max_request_body_size=settings.UPLOAD_FILE_MAX_SIZE * 4 // 3 + 8192,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=settings.MCP_ALLOWED_HOSTS,
            allowed_origins=settings.MCP_ALLOWED_ORIGINS,
        ),
    )
    # 手动 PAT 不声明 OAuth 授权服务器；仍使用 SDK 的 Bearer 校验与上下文。
    for route in app.routes:
        if getattr(route, "path", None) == "/mcp":
            route.app = RequireAuthMiddleware(route.app, required_scopes=["projects"])
    app.add_middleware(AuthContextMiddleware)
    app.add_middleware(AuthenticationMiddleware, backend=BearerAuthBackend(verifier))
    return app
