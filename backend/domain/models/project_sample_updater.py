from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Integer
from backend.common.db import Base


class ProjectSampleUpdater(Base):
    __tablename__ = "project_sample_updater"

    sample_id = Column(
        Integer,
        ForeignKey("project_sample.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )
    user_id = Column(
        Integer, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True, index=True
    )
    created_at = Column(
        DateTime(timezone=True),
        default=datetime.now,
        onupdate=datetime.now,
        nullable=False,
        comment="created time",
    )
