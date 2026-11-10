from fastapi import status

from backend.common.error_code import ErrorCode, YoloMcpException


def assert_project_access(project, current_user) -> None:
    """允许系统管理员、项目拥有者和协作者访问项目，其他用户返回 403。"""
    collaborator_ids = {c.id for c in project.collaborators}
    if (
        not current_user.is_admin
        and project.created_by != current_user.id
        and current_user.id not in collaborator_ids
    ):
        raise YoloMcpException(
            code=ErrorCode.CODE_30001_NO_PERMISSION,
            status_code=status.HTTP_403_FORBIDDEN,
        )


def assert_owner(resource, current_user) -> None:
    """配置、成员与正式数据删除仅允许资源拥有者或系统管理员。"""
    if resource.created_by != current_user.id and not current_user.is_admin:
        raise YoloMcpException(
            code=ErrorCode.CODE_30001_NO_PERMISSION,
            status_code=status.HTTP_403_FORBIDDEN,
        )
