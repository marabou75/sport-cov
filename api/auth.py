import os
import datetime
import bcrypt as _bcrypt_lib
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from pydantic import BaseModel
from jose import JWTError, jwt

_DATABASE_URL = os.getenv("DATABASE_URL", "").replace(
    "${DB_POSTGRESDB_PASSWORD}", os.getenv("DB_POSTGRESDB_PASSWORD", "")
)
_engine = create_engine(_DATABASE_URL, pool_pre_ping=True)
_SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
_Base = declarative_base()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "sportcov-secret-change-me-in-prod")
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 jours

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class UserORM(_Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    password_hash = Column(String, nullable=True)
    is_admin = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)


def _init_db():
    with _engine.connect() as conn:
        cols = [r[0] for r in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='users'"
        ))]
        if "is_admin" not in cols:
            conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT TRUE"))
            conn.commit()


_init_db()


def _get_db():
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _hash(pw: str) -> str:
    return _bcrypt_lib.hashpw(pw.encode(), _bcrypt_lib.gensalt()).decode()


def _verify(plain: str, hashed: str) -> bool:
    return _bcrypt_lib.checkpw(plain.encode(), hashed.encode())


def _make_token(user_id: int) -> str:
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    return jwt.encode({"sub": str(user_id), "exp": expire}, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(_get_db)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload.get("sub"))
    except (JWTError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Token invalide ou expiré")
    user = db.query(UserORM).filter(UserORM.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    return user


# ── Schémas Pydantic ──────────────────────────────────────────────

class RegisterIn(BaseModel):
    email: str
    full_name: str
    password: str


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    full_name: str
    email: str
    is_admin: bool


class UserOut(BaseModel):
    id: int
    email: str
    full_name: str
    is_admin: bool
    role: str = ""  # "admin" | "coach"


# ── Router ───────────────────────────────────────────────────────

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=LoginOut)
def register(req: RegisterIn, db: Session = Depends(_get_db)):
    if db.query(UserORM).filter(UserORM.email == req.email).first():
        raise HTTPException(status_code=400, detail="Cet email est déjà utilisé")
    user = UserORM(
        email=req.email,
        full_name=req.full_name,
        password_hash=_hash(req.password),
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return LoginOut(
        access_token=_make_token(user.id),
        full_name=user.full_name,
        email=user.email,
        is_admin=user.is_admin,
        role="admin" if user.is_admin else "coach",
    )


@router.post("/login", response_model=LoginOut)
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(_get_db)):
    user = db.query(UserORM).filter(UserORM.email == form.username).first()
    if not user or not user.password_hash or not _verify(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email ou mot de passe incorrect")
    return LoginOut(
        access_token=_make_token(user.id),
        full_name=user.full_name,
        email=user.email,
        is_admin=user.is_admin,
        role="admin" if user.is_admin else "coach",
    )


@router.get("/me", response_model=UserOut)
def me(current_user: UserORM = Depends(get_current_user)):
    role = "admin" if current_user.is_admin else "coach"
    return UserOut(id=current_user.id, email=current_user.email,
                   full_name=current_user.full_name, is_admin=current_user.is_admin, role=role)


@router.patch("/users/{user_id}/role")
def set_user_role(
    user_id: int,
    is_admin: bool,
    current_user: UserORM = Depends(get_current_user),
    db: Session = Depends(_get_db),
):
    """Admin only: promote or demote a user."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Réservé aux admins")
    user = db.query(UserORM).filter(UserORM.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    user.is_admin = is_admin
    db.commit()
    return {"id": user.id, "email": user.email, "is_admin": user.is_admin, "role": "admin" if is_admin else "coach"}
