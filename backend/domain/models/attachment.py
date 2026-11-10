from datetime import datetime

from sqlalchemy.schema import Index
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String

from backend.common.db import Base


class ProjectAttachment(Base):
    __tablename__ = "project_attachment"

    id = Column(Integer, primary_key=True, autoincrement=True)
    filename = Column(String(256), comment="file name")
    path = Column(String(256), comment="项目目录下的文件相对路径")
    project_id = Column(Integer, ForeignKey("project.id"), index=True)
    created_by = Column(Integer, ForeignKey("user.id"), index=True)
    updated_by = Column(Integer, ForeignKey("user.id"), index=True)
    created_at = Column(
        DateTime(timezone=True),
        default=datetime.now,
        comment="Time a project was created",
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now,
        onupdate=datetime.now,
        comment="Last time a project was updated",
    )
    deleted_at = Column(DateTime, index=True, comment="Project delete time")

    Index("idx_attachment_id_deleted_at", id, deleted_at)
