from sqlalchemy import Column, Integer, String, Boolean

from models.base import Base

class SarifSlice(Base):
    __tablename__ = 'sarif_slice'

    id = Column(Integer, primary_key=True)
    sarif_id = Column(String)
    result_path = Column(String)

    def __repr__(self):
        return f"<SarifSlice(id={self.id}, sarif_id={self.sarif_id}, result_path={self.result_path})>"