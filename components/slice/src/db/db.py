from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models.base import Base

class DBConnection:
    def __init__(self, db_url):
        self.engine = create_engine(db_url)
        self.Session = sessionmaker(bind=self.engine)
        Base.metadata.create_all(bind=self.engine)

    def write_to_db(self, obj):
        session = self.Session()
        session.add(obj)
        session.commit()
        session.close()
