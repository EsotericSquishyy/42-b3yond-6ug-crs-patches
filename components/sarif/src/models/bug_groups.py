from sqlalchemy import Column, Integer, String, Boolean, Time

from models.base import Base

class BugGroups(Base):
    __tablename__ = 'bug_groups'

    id = Column(Integer, primary_key=True)
    bug_id = Column(Integer)
    bug_profile_id = Column(Integer)
    created_at = Column(Time)
