from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, UniqueConstraint
from sqlalchemy.engine import URL  # Import URL for robust connection string creation
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import sys  # For printing to stderr
from dotenv import load_dotenv

# --- DIAGNOSTIC PRINT 1 ---
print(
    f"[DEBUG PRE-DOTENV] os.environ.get('SUPABASE_PORT'): '{os.environ.get('SUPABASE_PORT')}'",
    file=sys.stderr
)
# --- END DIAGNOSTIC PRINT 1 ---

load_dotenv()  # Load .env file for local development

# --- DIAGNOSTIC PRINT 2 ---
print(
    f"[DEBUG POST-DOTENV] os.environ.get('SUPABASE_PORT'): '{os.environ.get('SUPABASE_PORT')}'",
    file=sys.stderr
)
# --- END DIAGNOSTIC PRINT 2 ---

# Determine database connection type
DB_CONNECTION_TYPE = os.environ.get('DB_CONNECTION_TYPE', 'SQLITE').upper()

if DB_CONNECTION_TYPE == 'SUPABASE':
    SUPABASE_HOST = os.environ.get('SUPABASE_HOST')
    SUPABASE_RAW_PASSWORD = os.environ.get('SUPABASE_PASSWORD')  # Get the raw password
    SUPABASE_USER = os.environ.get('SUPABASE_USER', 'postgres')
    SUPABASE_PORT = os.environ.get('SUPABASE_PORT', '5432')  # Default if not found AFTER dotenv
    SUPABASE_DB_NAME = os.environ.get('SUPABASE_DB_NAME', 'postgres')

    # --- DIAGNOSTIC PRINT 3 ---
    print(
        f"[DEBUG IN-SUPABASE-IF] SUPABASE_PORT variable value: '{SUPABASE_PORT}'",
        file=sys.stderr
    )
    # --- END DIAGNOSTIC PRINT 3 ---

    if not all([SUPABASE_HOST, SUPABASE_RAW_PASSWORD]):
        print(
            "CRITICAL WARNING: DB_CONNECTION_TYPE is SUPABASE, but SUPABASE_HOST or "
            "SUPABASE_PASSWORD is not set. Falling back to SQLite.",
            file=sys.stderr
        )
        DATABASE_URL_STR = 'sqlite:///dread_system.db'
    else:
        try:
            db_url_obj = URL.create(
                drivername="postgresql+psycopg2",
                username=SUPABASE_USER,
                password=SUPABASE_RAW_PASSWORD,
                host=SUPABASE_HOST,
                port=int(SUPABASE_PORT),  # Port should be an integer
                database=SUPABASE_DB_NAME
            )
            DATABASE_URL_STR = db_url_obj.render_as_string(hide_password=False)
            print(
                f"[INFO] Connecting to Supabase PostgreSQL database: "
                f"{db_url_obj.render_as_string(hide_password=True)}",
                file=sys.stderr
            )
        except ValueError as e:
            print(
                f"[ERROR] Failed to convert SUPABASE_PORT to int. Value was: '{SUPABASE_PORT}'. Error: {e}",
                file=sys.stderr
            )
            print(
                "CRITICAL WARNING: Falling back to SQLite due to SUPABASE_PORT conversion error.",
                file=sys.stderr
            )
            DATABASE_URL_STR = 'sqlite:///dread_system.db'
elif DB_CONNECTION_TYPE == 'SQLITE':
    DATABASE_URL_STR = 'sqlite:///dread_system.db'
    print(f"[INFO] Using SQLite database: {DATABASE_URL_STR}", file=sys.stderr)
else:
    print(
        f"CRITICAL WARNING: Unknown DB_CONNECTION_TYPE '{DB_CONNECTION_TYPE}'. Falling back to SQLite.",
        file=sys.stderr
    )
    DATABASE_URL_STR = 'sqlite:///dread_system.db'

engine = create_engine(DATABASE_URL_STR)
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
