# db.py
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL manquante (variable d'environnement).")

# Engine SQLAlchemy
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Fabrique de sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base pour les modèles ORM
Base = declarative_base()


# Dépendance FastAPI pour obtenir une session DB par requête
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
