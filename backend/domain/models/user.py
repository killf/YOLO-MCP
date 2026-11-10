from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from backend.common.db import Base


class User(Base):
    __tablename__ = "user"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, index=True)
    hashed_password = Column(String(255))
    is_admin = Column(
        Boolean,
        nullable=False,
        default=False,
        server_default="0",
        comment="系统管理员可管理全部用户与项目",
    )
    is_active = Column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
        comment="停用账号拒绝全部认证",
    )
    auth_version = Column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
        comment="密码重置或停用时递增，使旧会话与预览签名失效",
    )
    created_at = Column(
        DateTime(timezone=True),
        default=datetime.now,
        comment="Time the user was created",
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now,
        comment="Last time the user was updated",
    )
    projects = relationship(
        "Project", secondary="project_collaborator", back_populates="collaborators"
    )
