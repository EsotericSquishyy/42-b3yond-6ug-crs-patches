from datetime import datetime
import enum

from sqlalchemy import (
    Integer,
    String,
    Boolean,
    DateTime,
    Text,
    BigInteger,
    Float,
    Enum,
    Sequence,
    JSON,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Define the new declarative base.
class Base(DeclarativeBase):
    pass

# Define Python Enums for the custom PostgreSQL enum types

class FuncTestStatusEnum(enum.Enum):
    SUCCESS = "SUCCESS"
    FAIL = "FAIL"
    HOLD = "HOLD"

class FuzzerTypeEnum(enum.Enum):
    seedgen = "seedgen"
    prime = "prime"
    general = "general"
    directed = "directed"
    corpus = "corpus"
    seedmini = "seedmini"

# class SanitizerEnum(enum.Enum):
#     ASAN = "ASAN"
#     UBSAN = "UBSAN"
#     MSAN = "MSAN"
#     JAZZER = "JAZZER"
#     UNKNOWN = "UNKNOWN"

class SourceTypeEnum(enum.Enum):
    repo = "repo"
    fuzz_tooling = "fuzz_tooling"
    diff = "diff"

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

class SubmissionStatusEnum(enum.Enum):
    accepted = "accepted"
    passed = "passed"
    failed = "failed"
    deadline_exceeded = "deadline_exceeded"
    errored = "errored"
    inconclusive = "inconclusive"

# Define models using mapped_column

class BugGroup(Base):
    __tablename__ = "bug_groups"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bug_id: Mapped[int] = mapped_column(Integer, nullable=False)
    bug_profile_id: Mapped[int] = mapped_column(Integer, nullable=False)
    diff_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class BugProfile(Base):
    __tablename__ = "bug_profiles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    harness_name: Mapped[str] = mapped_column(Text, nullable=False)
    sanitizer_bug_type: Mapped[str] = mapped_column(Text, nullable=False)
    trigger_point: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)

class Bug(Base):
    __tablename__ = "bugs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    architecture: Mapped[str] = mapped_column(String, nullable=False)
    poc: Mapped[str] = mapped_column(Text, nullable=False)
    harness_name: Mapped[str] = mapped_column(Text, nullable=False)
    sanitizer: Mapped[str] = mapped_column(Text, nullable=False)
    sarif_report: Mapped[dict] = mapped_column(JSONB)

class BugProfileStatus(Base):
    __tablename__ = "bug_profile_status"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bug_profile_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SubmissionStatusEnum] = mapped_column(Enum(SubmissionStatusEnum, name="submissionstatusenum"), nullable=False)

class DirectedSlice(Base):
    __tablename__ = "directed_slice"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    directed_id: Mapped[str] = mapped_column(String)
    result_path: Mapped[str] = mapped_column(String)

class FlywaySchemaHistory(Base):
    __tablename__ = "flyway_schema_history"
    installed_rank: Mapped[int] = mapped_column(
        Integer, primary_key=True
    )
    version: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    script: Mapped[str] = mapped_column(String(1000), nullable=False)
    checksum: Mapped[int] = mapped_column(Integer)
    installed_by: Mapped[str] = mapped_column(String(100), nullable=False)
    installed_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    execution_time: Mapped[int] = mapped_column(Integer, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)

class FuncTest(Base):
    __tablename__ = "func_test"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    project_name: Mapped[str] = mapped_column(String, nullable=False)
    test_cmd: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class FuncTestResult(Base):
    __tablename__ = "func_test_result"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    result: Mapped[FuncTestStatusEnum] = mapped_column(Enum(FuncTestStatusEnum, name="functeststatusenum"), nullable=False)

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    message_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class PatchBug(Base):
    __tablename__ = "patch_bugs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    bug_id: Mapped[int] = mapped_column(Integer, nullable=False)
    repaired: Mapped[bool] = mapped_column(Boolean, nullable=False)

class PatchDebug(Base):
    __tablename__ = "patch_debug"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

class Patch(Base):
    __tablename__ = "patches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bug_profile_id: Mapped[int] = mapped_column(Integer, nullable=False)
    patch: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class PatchStatus(Base):
    __tablename__ = "patch_status"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[SubmissionStatusEnum] = mapped_column(Enum(SubmissionStatusEnum, name="submissionstatusenum"), nullable=False)
    functionality_tests_passing: Mapped[bool] = mapped_column(Boolean)

class PatchSubmit(Base):
    __tablename__ = "patch_submit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    patch_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class SarifResult(Base):
    __tablename__ = "sarif_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    sarif_id: Mapped[str] = mapped_column(String, nullable=False)
    # this can be null if the result is incorrect
    bug_profile_id: Mapped[int] = mapped_column(Integer, nullable=True)
    result: Mapped[bool] = mapped_column(Boolean)
    description: Mapped[str] = mapped_column(String)

class SarifSlice(Base):
    __tablename__ = "sarif_slice"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sarif_id: Mapped[str] = mapped_column(String)
    result_path: Mapped[str] = mapped_column(String)

class Sarif(Base):
    __tablename__ = "sarifs"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    message_id: Mapped[str] = mapped_column(String, nullable=False)
    sarif: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Use a different attribute name for the "metadata" column to avoid conflicts.
    meta: Mapped[dict] = mapped_column("metadata", JSON)

class Seed(Base):
    __tablename__ = "seeds"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    path: Mapped[str] = mapped_column(Text)
    harness_name: Mapped[str] = mapped_column(Text)
    fuzzer: Mapped[FuzzerTypeEnum] = mapped_column(Enum(FuzzerTypeEnum, name="fuzzertypeenum"))
    instance: Mapped[str] = mapped_column(Text, server_default="default")
    coverage: Mapped[float] = mapped_column(Float)
    metric: Mapped[dict] = mapped_column(JSONB)

class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[SourceTypeEnum] = mapped_column(Enum(SourceTypeEnum, name="sourcetypeenum"), nullable=False)
    url: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String)

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    message_id: Mapped[str] = mapped_column(String, nullable=False)
    deadline: Mapped[int] = mapped_column(BigInteger, nullable=False)
    focus: Mapped[str] = mapped_column(String, nullable=False)
    project_name: Mapped[str] = mapped_column(String, nullable=False)
    task_type: Mapped[TaskTypeEnum] = mapped_column(Enum(TaskTypeEnum, name="tasktypeenum"), nullable=False)
    status: Mapped[TaskStatusEnum] = mapped_column(Enum(TaskStatusEnum, name="taskstatusenum"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # Remap the reserved "metadata" column to "meta" attribute.
    meta: Mapped[dict] = mapped_column("metadata", JSON)

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String, nullable=False)
    password: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
