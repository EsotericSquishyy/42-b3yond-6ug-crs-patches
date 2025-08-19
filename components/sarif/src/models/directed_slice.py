from sqlalchemy import Column, Integer, String, Boolean

from models.base import Base

class DirectedSlice(Base):
    __tablename__ = 'directed_slice'

    id = Column(Integer, primary_key=True)
    directed_id = Column(String)
    result_path = Column(String)