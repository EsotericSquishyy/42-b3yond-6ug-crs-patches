from sqlalchemy import Column, Integer, String, Boolean

from db.models.base import Base

class SarifSlice(Base):
    __tablename__ = 'sarif_slice'

    id = Column(Integer, primary_key=True)
    sarif_id = Column(String)
    result_path = Column(String)