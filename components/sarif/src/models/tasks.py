from sqlalchemy import Column, Integer, String, Boolean, BigInteger, DateTime, JSON, Enum, func, Enum
from sqlalchemy.orm import Mapped, mapped_column
import enum

from models.base import Base

class TaskStatusEnum(enum.Enum):
    canceled = "canceled"
    errored = "errored"
    pending = "pending"
    processing = "processing"
    succeeded = "succeeded"
    failed = "failed"
    waiting = "waiting"

class TaskTypeEnum(enum.Enum):
    full = "full"
    delta = "delta"

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(String, primary_key=True)
    user_id = Column(Integer, nullable=False)
    message_id = Column(String, nullable=False)
    deadline = Column(BigInteger, nullable=False)
    focus = Column(String, nullable=False)
    project_name = Column(String, nullable=False)
    task_type = Column(Enum(TaskTypeEnum, name="tasktypeenum"), nullable=False)
    status = Column(Enum(TaskStatusEnum, name="taskstatusenum"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    meta = Column("metadata", JSON)