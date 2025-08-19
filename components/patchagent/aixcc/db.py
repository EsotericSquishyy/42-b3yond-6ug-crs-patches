import enum
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy import (
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from aixcc.env import DB_URL

# --- Enums ---


class TaskTypeEnum(enum.Enum):
    full = "full"
    delta = "delta"


class TaskStatusEnum(enum.Enum):
    canceled = "canceled"
    errored = "errored"
    pending = "pending"
    processing = "processing"
    succeeded = "succeeded"
    failed = "failed"
    waiting = "waiting"


class SourceTypeEnum(enum.Enum):
    repo = "repo"
    fuzz_tooling = "fuzz_tooling"
    diff = "diff"


class FuzzerTypeEnum(enum.Enum):
    seedgen = "seedgen"
    prime = "prime"
    general = "general"
    directed = "directed"
    corpus = "corpus"
    seedmini = "seedmini"
    seedcodex = "seedcodex"


class SubmissionStatusEnum(enum.Enum):
    accepted = "accepted"
    passed = "passed"
    failed = "failed"
    deadline_exceeded = "deadline_exceeded"
    errored = "errored"


# --- Base ---


class Base(DeclarativeBase): ...


# --- Models ---


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    password: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    # A user may create many tasks.
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="user")


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    message_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    # A message can be referenced by one or more tasks and associated with many SARIF reports.
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="message", foreign_keys=lambda: [Task.message_id])
    sarifs: Mapped[List["Sarif"]] = relationship("Sarif", back_populates="message", foreign_keys=lambda: [Sarif.message_id])


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    message_id: Mapped[str] = mapped_column(String, ForeignKey("messages.id"), nullable=False)
    deadline: Mapped[int] = mapped_column(BigInteger, nullable=False)
    focus: Mapped[str] = mapped_column(String, nullable=False)
    project_name: Mapped[str] = mapped_column(String, nullable=False)
    task_type: Mapped[TaskTypeEnum] = mapped_column(SAEnum(TaskTypeEnum, name="tasktypeenum"), nullable=False)
    status: Mapped[TaskStatusEnum] = mapped_column(SAEnum(TaskStatusEnum, name="taskstatusenum"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    metadata_: Mapped[Optional[Dict]] = mapped_column("metadata", JSONB)
    # NOTE: the metadata_ column is used to avoid the following error:
    # sqlalchemy.exc.InvalidRequestError: Attribute name 'metadata' is reserved when using the Declarative API

    user: Mapped["User"] = relationship("User", back_populates="tasks")
    message: Mapped["Message"] = relationship("Message", back_populates="tasks", foreign_keys=[message_id])
    sources: Mapped[List["Source"]] = relationship("Source", back_populates="task", cascade="all, delete-orphan")
    sarifs: Mapped[List["Sarif"]] = relationship("Sarif", back_populates="task", cascade="all, delete-orphan")
    seeds: Mapped[List["Seed"]] = relationship("Seed", back_populates="task", cascade="all, delete-orphan")
    bugs: Mapped[List["Bug"]] = relationship("Bug", back_populates="task", cascade="all, delete-orphan")
    bug_profiles: Mapped[List["BugProfile"]] = relationship("BugProfile", back_populates="task", cascade="all, delete-orphan")
    patch_submit_timestamps: Mapped[List["PatchSubmitTimestamp"]] = relationship("PatchSubmitTimestamp", back_populates="task", cascade="all, delete-orphan")


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, ForeignKey("tasks.id"), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[SourceTypeEnum] = mapped_column(SAEnum(SourceTypeEnum, name="sourcetypeenum"), nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[Optional[str]] = mapped_column(String)

    task: Mapped["Task"] = relationship("Task", back_populates="sources")


class Sarif(Base):
    __tablename__ = "sarifs"

    id: Mapped[str] = mapped_column(String, primary_key=True, nullable=False)
    task_id: Mapped[str] = mapped_column(String, ForeignKey("tasks.id"), nullable=False)
    message_id: Mapped[str] = mapped_column(String, ForeignKey("messages.id"), nullable=False)
    sarif: Mapped[Dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    metadata_: Mapped[Optional[Dict]] = mapped_column("metadata", JSONB)
    # NOTE: the metadata_ column is used to avoid the following error:
    # sqlalchemy.exc.InvalidRequestError: Attribute name 'metadata' is reserved when using the Declarative API

    task: Mapped["Task"] = relationship("Task", back_populates="sarifs")
    message: Mapped["Message"] = relationship("Message", back_populates="sarifs", foreign_keys=[message_id])


class Seed(Base):
    __tablename__ = "seeds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, ForeignKey("tasks.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    path: Mapped[Optional[str]] = mapped_column(Text)
    harness_name: Mapped[Optional[str]] = mapped_column(Text)
    fuzzer: Mapped[Optional[FuzzerTypeEnum]] = mapped_column(SAEnum(FuzzerTypeEnum, name="fuzzertypeenum"))
    instance: Mapped[Optional[str]] = mapped_column(Text, default="default")
    coverage: Mapped[Optional[float]] = mapped_column(Float)
    metric: Mapped[Optional[Dict]] = mapped_column(JSONB)

    task: Mapped["Task"] = relationship("Task", back_populates="seeds")


class Bug(Base):
    __tablename__ = "bugs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, ForeignKey("tasks.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())
    architecture: Mapped[str] = mapped_column(String, nullable=False)
    poc: Mapped[str] = mapped_column(Text, nullable=False)
    harness_name: Mapped[str] = mapped_column(Text, nullable=False)
    sanitizer: Mapped[str] = mapped_column(String, nullable=False)
    sarif_report: Mapped[Optional[Dict]] = mapped_column(JSONB)

    task: Mapped["Task"] = relationship("Task", back_populates="bugs")
    bug_groups: Mapped[List["BugGroup"]] = relationship("BugGroup", back_populates="bug", cascade="all, delete-orphan")
    patch_bugs: Mapped[List["PatchBug"]] = relationship("PatchBug", back_populates="bug", cascade="all, delete-orphan")


class BugProfile(Base):
    __tablename__ = "bug_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, ForeignKey("tasks.id"), nullable=False)
    harness_name: Mapped[str] = mapped_column(Text, nullable=False)
    sanitizer: Mapped[str] = mapped_column(String, nullable=False)
    sanitizer_bug_type: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_point: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

    task: Mapped["Task"] = relationship("Task", back_populates="bug_profiles")
    bug_groups: Mapped[List["BugGroup"]] = relationship("BugGroup", back_populates="bug_profile", cascade="all, delete-orphan")
    patches: Mapped[List["Patch"]] = relationship("Patch", back_populates="bug_profile", cascade="all, delete-orphan")
    bug_profile_statuses: Mapped[List["BugProfileStatus"]] = relationship("BugProfileStatus", back_populates="bug_profile", cascade="all, delete-orphan")


class BugGroup(Base):
    __tablename__ = "bug_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bug_id: Mapped[int] = mapped_column(Integer, ForeignKey("bugs.id"), nullable=False)
    bug_profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("bug_profiles.id"), nullable=False)
    diff_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("bug_id", "bug_profile_id", name="_bug_bugprofile_uc"),)

    bug: Mapped["Bug"] = relationship("Bug", back_populates="bug_groups")
    bug_profile: Mapped["BugProfile"] = relationship("BugProfile", back_populates="bug_groups")


class BugProfileStatus(Base):
    __tablename__ = "bug_profile_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bug_profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("bug_profiles.id"), nullable=False)
    status: Mapped[SubmissionStatusEnum] = mapped_column(SAEnum(SubmissionStatusEnum, name="submissionstatusenum"), nullable=False)

    bug_profile: Mapped["BugProfile"] = relationship("BugProfile", back_populates="bug_profile_statuses")


class Patch(Base):
    __tablename__ = "patches"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bug_profile_id: Mapped[int] = mapped_column(Integer, ForeignKey("bug_profiles.id"), nullable=False)
    patch: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    bug_profile: Mapped["BugProfile"] = relationship("BugProfile", back_populates="patches")
    patch_bugs: Mapped[List["PatchBug"]] = relationship("PatchBug", back_populates="patch", cascade="all, delete-orphan")
    patch_statuses: Mapped[List["PatchStatus"]] = relationship("PatchStatus", back_populates="patch", cascade="all, delete-orphan")
    patch_submits: Mapped[List["PatchSubmit"]] = relationship("PatchSubmit", back_populates="patch", cascade="all, delete-orphan")


class PatchStatus(Base):
    __tablename__ = "patch_status"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patch_id: Mapped[int] = mapped_column(Integer, ForeignKey("patches.id"), nullable=False)
    status: Mapped[SubmissionStatusEnum] = mapped_column(SAEnum(SubmissionStatusEnum, name="submissionstatusenum"), nullable=False)
    functionality_tests_passing: Mapped[Optional[bool]] = mapped_column(Boolean)

    patch: Mapped["Patch"] = relationship("Patch", back_populates="patch_statuses")


class PatchBug(Base):
    __tablename__ = "patch_bugs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patch_id: Mapped[int] = mapped_column(Integer, ForeignKey("patches.id"), nullable=False)
    bug_id: Mapped[int] = mapped_column(Integer, ForeignKey("bugs.id"), nullable=False)
    repaired: Mapped[bool] = mapped_column(Boolean, nullable=False)

    __table_args__ = (UniqueConstraint("bug_id", "patch_id", name="_bug_patch_uc"),)

    patch: Mapped["Patch"] = relationship("Patch", back_populates="patch_bugs")
    bug: Mapped["Bug"] = relationship("Bug", back_populates="patch_bugs")


class PatchDebug(Base):
    __tablename__ = "patch_debug"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())


class PatchSubmit(Base):
    __tablename__ = "patch_submit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patch_id: Mapped[int] = mapped_column(Integer, ForeignKey("patches.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    patch: Mapped["Patch"] = relationship("Patch", back_populates="patch_submits")


class PatchSubmitTimestamp(Base):
    __tablename__ = "patch_submit_timestamp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, ForeignKey("tasks.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    task: Mapped["Task"] = relationship("Task", back_populates="patch_submit_timestamps")


# --- Database Connection ---

_engine = None


def make_session() -> Session:
    global _engine
    if _engine is None:
        _engine = create_engine(DB_URL)
        Base.metadata.create_all(_engine)
    return sessionmaker(_engine)()
