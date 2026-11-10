"""记录项目的本地训练参数、执行状态、日志与模型产出。"""

from datetime import datetime
from enum import Enum

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text

from backend.common.db import Base


class TrainingStatus(str, Enum):
    PENDING = "PENDING"

    RUNNING = "RUNNING"

    PAUSING = "PAUSING"

    PAUSED = "PAUSED"

    SUCCEEDED = "SUCCEEDED"

    FAILED = "FAILED"

    INTERRUPTED = "INTERRUPTED"


class TrainingRun(Base):
    __tablename__ = "training_run"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("user.id"), nullable=False)
    initial_model = Column(String(256), nullable=False)
    parameters = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default=TrainingStatus.PENDING.value)

    run_id = Column(String(128), nullable=True)
    model_name = Column(String(256), nullable=True)
    metrics = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.now)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
