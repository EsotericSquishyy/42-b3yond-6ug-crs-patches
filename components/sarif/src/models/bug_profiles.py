from sqlalchemy import Column, Integer, String, Boolean, Time

from models.base import Base

class BugProfiles(Base):
    __tablename__ = 'bug_profiles'

    id = Column(Integer, primary_key=True)
    task_id = Column(String, nullable=False)
    harness_name = Column(String, nullable=False)
    sanitizer = Column(String, nullable=False)
    sanitizer_bug_type = Column(String, nullable=False)
    trigger_point = Column(String, nullable=False)
    summary = Column(String, nullable=False)


