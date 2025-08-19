from sqlalchemy import Column, Integer, String, Boolean, Time

from models.base import Base

class Bugs(Base):
    __tablename__ = 'bugs'

    id = Column(Integer, primary_key=True)
    task_id = Column(String)
    created_at = Column(Time)
    architecture = Column(String)
    poc = Column(String)
    harness_name = Column(String)
    sanitizer = Column(String)
    sarif_report = Column(String)
