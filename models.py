from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship

DATABASE_URL = 'sqlite:///dread_system.db'

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class AreaDeathCount(Base):
    __tablename__ = 'area_death_counts'
    
    id = Column(Integer, primary_key=True, index=True)
    area_id = Column(String(100), unique=True, nullable=False, index=True)
    death_count = Column(Float, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)

class DreadLevel(Base):
    __tablename__ = 'dread_levels'
    
    id = Column(Integer, primary_key=True, index=True)
    area_id = Column(String(100), unique=True, nullable=False, index=True)
    level = Column(Integer, default=0)
    last_updated = Column(DateTime, default=datetime.utcnow)

class PlayerNote(Base):
    __tablename__ = 'player_notes'
    
    id = Column(Integer, primary_key=True, index=True)
    area_id = Column(String(100), nullable=False, index=True)
    note_location_id = Column(String(100), nullable=False)
    word = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Composite unique constraint for area_id and note_location_id
    __table_args__ = (
        UniqueConstraint('area_id', 'note_location_id', name='uq_player_note_location', sqlite_on_conflict='REPLACE'),
    )

def create_db_and_tables():
    Base.metadata.create_all(bind=engine) 