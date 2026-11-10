from enum import Enum
from datetime import datetime

from sqlalchemy.schema import Index
from sqlalchemy.orm import relationship
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from backend.common.db import Base


class SampleState(str, Enum):
    """
    project sample state
    """

    NEW = "NEW"

    SKIPPED = "SKIPPED"

    DONE = "DONE"


class DatasetSplit(str, Enum):
    TRAIN = "train"

    TEST = "test"


class ProjectSample(Base):
    __tablename__ = "project_sample"

    id = Column(Integer, primary_key=True, autoincrement=True)
    inner_id = Column(Integer, comment="sample id in a project")
    project_id = Column(Integer, ForeignKey("project.id"), index=True)
    file_id = Column(Integer, ForeignKey("project_attachment.id"), unique=True)
    split = Column(
        String(16),
        nullable=False,
        default=DatasetSplit.TRAIN.value,
        server_default="train",
        comment="训练集或测试集",
    )
    created_by = Column(Integer, ForeignKey("user.id"), index=True)
    updated_by = Column(Integer, ForeignKey("user.id"))
    created_at = Column(
        DateTime(timezone=True),
        default=datetime.now,
        comment="Time a project sample result was created",
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=datetime.now,
        onupdate=datetime.now,
        comment="Last time a project sample result was updated",
    )
    annotated_count = Column(
        Integer,
        default=0,
        comment="project sample result count",
    )
    data = Column(Text, comment="project sample result")
    state = Column(
        String(32),
        default=SampleState.NEW.value,
        comment="NEW is has not start yet, DONE is completed, SKIPPED is skipped",
    )
    deleted_at = Column(
        DateTime(timezone=True), index=True, comment="Project delete time"
    )

    # 由旧的data里的fileNames和urls中的唯一一个，迁移到media中
    file = relationship("ProjectAttachment", foreign_keys=[file_id])
    project = relationship("Project", foreign_keys=[project_id])
    owner = relationship("User", foreign_keys=[created_by])
    updaters = relationship("User", secondary="project_sample_updater")

    Index("idx_sample_id_deleted_at", id, deleted_at)
