from datetime import datetime

from sqlalchemy.schema import Index
from sqlalchemy.orm import relationship
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from backend.common.db import Base


class ProjectPreAnnotation(Base):
    __tablename__ = "project_pre_annotation"
    """Project pre-annotations for a sample of a project.
    """

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer, ForeignKey("project.id"), index=True, comment="Project ID"
    )
    sample_name = Column(
        String(255), index=True, comment="One of the sample names of the project"
    )
    file_id = Column(Integer, ForeignKey("project_attachment.id"), index=True)
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
        comment="Last time a project pre annotation result was updated",
    )
    data = Column(Text, comment="project sample pre annotation result")
    deleted_at = Column(
        DateTime(timezone=True),
        index=True,
        comment="Project pre-annotation delete time",
    )

    file = relationship("ProjectAttachment", foreign_keys=[file_id])
    project = relationship("Project", foreign_keys=[project_id])
    owner = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    Index("idx_pre_annotation_id_deleted_at", id, deleted_at)
