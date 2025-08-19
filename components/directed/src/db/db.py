from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db.models.base import Base

class DBConnection:
    def __init__(self, db_url):
        self.engine = create_engine(db_url)
        # Disable expiration so that objects remain accessible after commit.
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)
        self.current_session = None
        Base.metadata.create_all(bind=self.engine)
    
    def write_to_db(self, obj):
        session = self.Session()
        session.add(obj)
        session.commit()
        session.close()
    
    def clear_db(self):
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
    
    def read_from_db(self, obj):
        session = self.Session()
        results = session.query(obj).all()
        session.close()
        return results
    
    def execute_stmt(self, stmt):
        session = self.Session()
        result = session.execute(stmt).scalars().all()
        session.commit()
        session.close()
        return result
    
    def start_session(self):
        self.current_session = self.Session()
    
    def stop_session(self):
        self.current_session.close()
        self.current_session = None
    
    def execute_stmt_with_session(self, stmt):
        result = self.current_session.execute(stmt).scalars().all()
        self.current_session.commit()
        return result
