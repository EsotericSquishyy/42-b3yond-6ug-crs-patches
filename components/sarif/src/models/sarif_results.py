from sqlalchemy import Column, Integer, String, Boolean

from models.base import Base

class SarifResults(Base):
    __tablename__ = 'sarif_results'

    id = Column(Integer, primary_key=True)
    bug_profile_id = Column(Integer)
    task_id = Column(String)
    sarif_id = Column(String)
    result = Column(Boolean)
    description = Column(String)

    def __repr__(self):
        return f"<SarifResults(id={self.id}, sarif_id={self.sarif_id}, result={self.result})>"