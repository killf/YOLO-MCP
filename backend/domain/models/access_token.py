"""个人访问令牌只存摘要，认证时同时检查所属用户的当前权限。"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from backend.common.db import Base


class PersonalAccessToken(Base):
    __tablename__ = "access_token"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False, index=True)
    name = Column(String(64), nullable=False)
    token_hash = Column(String(64), nullable=False, unique=True)

    created_at = Column(DateTime, nullable=False, default=datetime.now)
    expires_at = Column(DateTime, nullable=True)
    last_used_at = Column(DateTime, nullable=True)
    revoked_at = Column(DateTime, nullable=True)
