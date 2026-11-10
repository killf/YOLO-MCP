from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer
from backend.common.db import Base


class ProjectCollaborator(Base):
    __tablename__ = "project_collaborator"

    project_id = Column(
        Integer,
        ForeignKey("project.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    user_id = Column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at = Column(
        DateTime(timezone=True),
        default=datetime.now,
        comment="Time a project collaborator was created",
    )
