import enum
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    BigInteger,
    Float,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    func,
    Enum as SQLEnum,
    JSON,
)
from sqlalchemy.dialects.postgresql import JSONB

from db.models.base import Base

# Define Python enums corresponding to the PostgreSQL enum types.
class TaskTypeEnum(enum.Enum):
    full = 'full'
    delta = 'delta'

class TaskStatusEnum(enum.Enum):
    canceled = 'canceled'
    errored = 'errored'
    pending = 'pending'
    processing = 'processing'
    succeeded = 'succeeded'
    failed = 'failed'
    waiting = 'waiting'

class SourceTypeEnum(enum.Enum):
    repo = 'repo'
    fuzz_tooling = 'fuzz_tooling'
    diff = 'diff'

class FuzzerTypeEnum(enum.Enum):
    seedgen = 'seedgen'
    prime = 'prime'
    general = 'general'
    directed = 'directed'
    corpus = 'corpus'
    seedmini = 'seedmini'

# [deprecated] Has been replaced by sanitizer in the bug table.
class SanitizerEnum(enum.Enum):
    ASAN = 'address'
    UBSAN = 'undefined'
    MSAN = 'memory'
    JAZZER = 'none'
    UNKNOWN = 'unknown'

# CRS basic tables

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Message(Base):
    __tablename__ = 'messages'
    id = Column(String, primary_key=True)
    message_time = Column(BigInteger, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    message_id = Column(String, ForeignKey('messages.id'), nullable=False)
    deadline = Column(BigInteger, nullable=False)
    focus = Column(String, nullable=False)
    project_name = Column(String, nullable=False)
    task_type = Column(SQLEnum(TaskTypeEnum, name='tasktypeenum'), nullable=False)
    status = Column(SQLEnum(TaskStatusEnum, name='taskstatusenum'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # "metadata" is a reserved name, so we map it to metadata_json.
    metadata_json = Column('metadata', JSON)

class Source(Base):
    __tablename__ = 'sources'
    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey('tasks.id'), nullable=False)
    sha256 = Column(String(64), nullable=False)
    source_type = Column(SQLEnum(SourceTypeEnum, name='sourcetypeenum'), nullable=False)
    url = Column(String, nullable=False)
    path = Column(String)

class Sarif(Base):
    __tablename__ = 'sarifs'
    id = Column(String, primary_key=True)
    task_id = Column(String, ForeignKey('tasks.id'), nullable=False)
    message_id = Column(String, ForeignKey('messages.id'), nullable=False)
    sarif = Column(JSONB, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    # Again, avoid using "metadata" as an attribute name.
    metadata_json = Column('metadata', JSON)

# Fuzzing tables

class Seed(Base):
    __tablename__ = 'seeds'
    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey('tasks.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    path = Column(Text)
    harness_name = Column(Text)
    fuzzer = Column(SQLEnum(FuzzerTypeEnum, name='fuzzertypeenum'))
    instance = Column(Text)
    coverage = Column(Float)
    metric = Column(JSONB)

class Bug(Base):
    __tablename__ = 'bugs'
    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey('tasks.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    architecture = Column(String, nullable=False)
    poc = Column(Text, nullable=False)
    harness_name = Column(Text, nullable=False)
    sanitizer = Column(String, nullable=False)
    sarif_report = Column(JSONB)

# Triage tables

class BugProfile(Base):
    __tablename__ = 'bug_profiles'
    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey('tasks.id'), nullable=False)
    harness_name = Column(Text, nullable=False)
    sanitizer_bug_type = Column(Text, nullable=False)
    trigger_point = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)

class BugGroup(Base):
    __tablename__ = 'bug_groups'
    id = Column(Integer, primary_key=True)
    bug_id = Column(Integer, ForeignKey('bugs.id'), nullable=False)
    bug_profile_id = Column(Integer, ForeignKey('bug_profiles.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        UniqueConstraint('bug_id', 'bug_profile_id', name='_bug_bugprofile_uc'),
    )

# SARIF tables

class SarifResult(Base):
    __tablename__ = 'sarif_results'
    id = Column(Integer, primary_key=True)
    sarif_id = Column(String)
    result = Column(Boolean)

# Patch tables

class Patch(Base):
    __tablename__ = 'patches'
    id = Column(Integer, primary_key=True)
    bug_profile_id = Column(Integer, ForeignKey('bug_profiles.id'), nullable=False)
    patch = Column(Text, nullable=False)

class PatchBug(Base):
    __tablename__ = 'patch_bugs'
    id = Column(Integer, primary_key=True)
    patch_id = Column(Integer, ForeignKey('patches.id'), nullable=False)
    bug_id = Column(Integer, ForeignKey('bugs.id'), nullable=False)
    repaired = Column(Boolean, nullable=False)
    __table_args__ = (
        UniqueConstraint('bug_id', 'patch_id', name='_bug_patch_uc'),
    )

class PatchRecord(Base):
    __tablename__ = 'patch_records'
    id = Column(Integer, primary_key=True)
    project = Column(String, nullable=False)
    bug_profile_id = Column(Integer, ForeignKey('bug_profiles.id'), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

class PatchException(Base):
    __tablename__ = 'patch_exceptions'
    id = Column(Integer, primary_key=True)
    exception = Column(String, nullable=False)

# Function test tables

class FuncTest(Base):
    __tablename__ = 'func_test'
    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey('tasks.id'), nullable=False)
    project_name = Column(String, nullable=False)
    test_cmd = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
