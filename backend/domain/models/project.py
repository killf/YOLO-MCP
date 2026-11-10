from enum import Enum
from datetime import datetime

from sqlalchemy.schema import Index
from sqlalchemy.orm import relationship
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, JSON

from backend.common.db import Base


class ProjectStatus(str, Enum):
    """
    project status
    """

    DRAFT = "DRAFT"

    IMPORTED = "IMPORTED"

    CONFIGURED = "CONFIGURED"

    INPROGRESS = "INPROGRESS"

    FINISHED = "FINISHED"


class MediaType(str, Enum):
    """
    project meida type
    """

    IMAGE = "IMAGE"

    VIDEO = "VIDEO"

    AUDIO = "AUDIO"


class Project(Base):
    __tablename__ = "project"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), index=True)
    description = Column(String(1024), comment="project description")
    tips = Column(String(1024), comment="project tips")
    ai_model_name = Column(
        String(1024), nullable=True, comment="自动标注的权重文件名或官方模型 ID"
    )

    ai_algorithm = Column(
        String(32), nullable=False, default="yolo", server_default="yolo"
    )
    training_config = Column(JSON, nullable=True, comment="开始训练时使用的默认参数")

    @property
    def dataset_prefix(self) -> str:
        """项目 ID 决定固定的本地目录，不随名称或配置变化。"""
        return f"projects/{self.id}"

    last_sample_inner_id = Column(
        Integer, default=0, comment="The last inner id of sample in a project"
    )
    config = Column(Text, comment="project config yaml")
    media_type = Column(
        String(32),
        comment="project media type: image, video, audio",
    )
    status = Column(
        String(32), default=ProjectStatus.DRAFT.value, comment="project status"
    )
    created_by = Column(Integer, ForeignKey(column="user.id"), index=True)
    updated_by = Column(
        Integer,
        ForeignKey(column="user.id"),
        comment="Last time a project was updated by",
    )
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
    deleted_at = Column(
        DateTime(timezone=True), index=True, comment="Project delete time"
    )

    collaborators = relationship(
        "User", secondary="project_collaborator", back_populates="projects"
    )
    owner = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    Index("idx_project_id_deleted_at_index", id, deleted_at)
