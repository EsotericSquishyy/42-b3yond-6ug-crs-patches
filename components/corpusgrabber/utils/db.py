from sqlalchemy import (
    Column,
    Integer,
    NullPool,
    String,
    BigInteger,
    Boolean,
    Text,
    ForeignKey,
    UniqueConstraint,
    create_engine,
    func,
    Float,
)
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, ENUM

# Create the declarative base class
Base = declarative_base()

# Define PostgreSQL ENUM types
TaskTypeEnum = ENUM('full', 'delta', name='tasktypeenum')
TaskStatusEnum = ENUM('canceled', 'errored', 'pending', 'processing', 'succeeded', 'failed', 'waiting', name='taskstatusenum')
SourceTypeEnum = ENUM('repo', 'fuzz_tooling', 'diff', name='sourcetypeenum')
FuzzerTypeEnum = ENUM('seedgen', 'prime', 'general', 'directed', 'corpus', name='fuzzertypeenum')

# CRS basic tables

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)  # serial maps to auto-incrementing Integer
    username = Column(String, nullable=False, unique=True)
    password = Column(String, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Message(Base):
    __tablename__ = 'messages'
    id = Column(String, primary_key=True)
    message_time = Column(BigInteger, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(String, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    message_id = Column(String, ForeignKey('messages.id'), nullable=False)
    deadline = Column(BigInteger, nullable=False)
    focus = Column(String, nullable=False)
    project_name = Column(String, nullable=False)
    task_type = Column(TaskTypeEnum, nullable=False)
    status = Column(TaskStatusEnum, nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    metadata_ = Column("metadata", JSONB)

    # Relationships
    user = relationship('User')
    message = relationship('Message')

class Source(Base):
    __tablename__ = 'sources'
    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey('tasks.id'), nullable=False)
    sha256 = Column(String(64), nullable=False)  # varchar(64) specifies length
    source_type = Column(SourceTypeEnum, nullable=False)
    url = Column(String, nullable=False)
    path = Column(String)  # varchar without length maps to String

    # Relationship
    task = relationship('Task')

# Component specific tables

class Seed(Base):
    __tablename__ = 'seeds'
    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey('tasks.id'), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    path = Column(String)  # text maps to String
    harness_name = Column(String)  # text maps to String
    fuzzer = Column(FuzzerTypeEnum)
    coverage = Column(Float)  # double precision maps to Float
    metric = Column(JSONB)

    # Relationship
    task = relationship('Task')

class Bug(Base):
    __tablename__ = 'bugs'
    id = Column(Integer, primary_key=True)
    task_id = Column(String, ForeignKey('tasks.id'), nullable=False)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
    architecture = Column(String, nullable=False)
    poc = Column(String, nullable=False)  # text maps to String
    harness_name = Column(String, nullable=False)  # text maps to String
    sanitizer = Column(String, nullable=False)
    sarif_report = Column(JSONB)

    # Relationship
    task = relationship('Task')


def connect_database(database_url):
    engine = create_engine(database_url, poolclass=NullPool)

    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
