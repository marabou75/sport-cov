# main.py
from typing import Tuple, List, Optional
import urllib.parse
import os
import uuid
import datetime
import tempfile
import httpx

import requests
from dotenv import load_dotenv
from functools import lru_cache
from itertools import combinations

from fastapi import FastAPI
from auth import router as auth_router, get_current_user, UserORM, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Float,
    Boolean,
    ForeignKey,
    DateTime,
    Text,
    text,
    select,
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship, Session

from jinja2 import Template
from weasyprint import HTML, CSS

# -------------------------------------------------------------------
# 1) CONFIG GLOBALE
# -------------------------------------------------------------------
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

CO2_PER_KM = float(os.getenv("CO2_PER_KM", "0.2"))            # kg/km
MAX_PASSENGERS = int(os.getenv("MAX_PASSENGERS", "3"))        # passagers max
SEUIL_RALLONGE = float(os.getenv("SEUIL_RALLONGE", "1.5"))    # facteur x trajet direct

LOGO_URL_DEFAULT = os.getenv("LOGO_URL", "").strip()

CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "5.0"))
READ_TIMEOUT = float(os.getenv("READ_TIMEOUT", "30.0"))
REQUESTS_TOTAL_RETRIES = int(os.getenv("REQUESTS_TOTAL_RETRIES", "5"))
REQUESTS_BACKOFF = float(os.getenv("REQUESTS_BACKOFF", "0.7"))

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL manquante. Exemple : "
        "postgresql+psycopg2://sportcov:<mdp>@n8n-postgres:5432/sportcov"
    )

N8N_WEBHOOK_URL = os.getenv(
    "N8N_WEBHOOK_URL",
    "http://n8n:5678/webhook/carpool",  # URL interne Docker par défaut
)


# -------------------------------------------------------------------
# 2) SQLALCHEMY : ENGINE / SESSION / BASE
# -------------------------------------------------------------------
engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# -------------------------------------------------------------------
# 3) ORM (tables principales)
# -------------------------------------------------------------------
class TeamORM(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False)
    logo_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    events = relationship("EventORM", back_populates="team", cascade="all, delete-orphan")
    participants = relationship("ParticipantORM", back_populates="team", cascade="all, delete-orphan")


class ParticipantORM(Base):
    __tablename__ = "participants"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    name = Column(String(255), nullable=False)
    address = Column(Text, nullable=False)
    postal_code = Column(String(32), nullable=True)   # ✅ nouveau
    city = Column(String(255), nullable=True)  
    email = Column(String(255), nullable=True)
    telephone = Column(String(64), nullable=True)
    token = Column(String(32), unique=True, nullable=False, default=lambda: uuid.uuid4().hex[:24])
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    team = relationship("TeamORM", back_populates="participants")


class EventORM(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    title = Column(String(255), nullable=True)
    destination = Column(Text, nullable=False)
    event_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    team = relationship("TeamORM", back_populates="events")
    trips = relationship("TripORM", back_populates="event", cascade="all, delete-orphan")
    co2_entries = relationship("TripCO2ORM", back_populates="event", cascade="all, delete-orphan")


class TripORM(Base):
    __tablename__ = "trips"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    voiture = Column(String(64), nullable=False)
    conducteur = Column(String(255), nullable=False)
    email_conducteur = Column(String(255), nullable=True)
    telephone_conducteur = Column(String(64), nullable=True)
    ordre = Column(Text, nullable=False)
    google_maps = Column(Text, nullable=False)

    event = relationship("EventORM", back_populates="trips")
    passengers = relationship(
        "TripPassengerORM", back_populates="trip", cascade="all, delete-orphan"
    )


class TripPassengerORM(Base):
    __tablename__ = "trip_passengers"

    id = Column(Integer, primary_key=True, index=True)
    trip_id = Column(Integer, ForeignKey("trips.id"), nullable=False)
    nom = Column(String(255), nullable=False)
    marche = Column(Boolean, default=False)
    email = Column(String(255), nullable=True)
    telephone = Column(String(64), nullable=True)

    trip = relationship("TripORM", back_populates="passengers")


class TripCO2ORM(Base):
    __tablename__ = "trip_co2"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    voiture = Column(String(64), nullable=False)
    conducteur = Column(String(255), nullable=False)
    email_conducteur = Column(String(255), nullable=True)
    nb_passagers = Column(Integer, nullable=False)
    co2_voiture_kg = Column(Float, nullable=False)

    event = relationship("EventORM", back_populates="co2_entries")


# -------------------------------------------------------------------
# 4) Pydantic modèles (entrée/sortie API)
# -------------------------------------------------------------------
class Participant(BaseModel):
    name: str
    address: str
    email: str = ""
    telephone: str = ""


class ParticipantOut(BaseModel):
    id: int
    name: str
    address: str
    postal_code: str | None = None   # ✅
    city: str | None = None 
    email: str | None = None
    telephone: str | None = None
    token: str = ""

    class Config:
        from_attributes = True

class ParticipantCreate(BaseModel):
    name: str
    address: str
    postal_code: str | None = None   # ✅
    city: str | None = None 
    email: str | None = None
    telephone: str | None = None


class ParticipantUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    postal_code: str | None = None   # ✅
    city: str | None = None
    email: str | None = None
    telephone: str | None = None


class InputData(BaseModel):
    participants: List[Participant]
    destination: str

class CarpoolRequest(BaseModel):
    event_address: str
    participant_ids: List[int]
    event_title: Optional[str] = None

class OptimizeAndSavePayload(InputData):
    team_name: str
    team_city: Optional[str] = None
    team_category: Optional[str] = None  # pas encore stockés mais gardés pour plus tard


class Co2Voiture(BaseModel):
    voiture: str
    conducteur: str
    email_conducteur: str = ""
    nb_passagers: int
    co2_voiture_kg: float


class TrajetPassager(BaseModel):
    nom: str
    marche: bool = False
    email: str = ""
    telephone: str = ""


class TrajetOut(BaseModel):
    voiture: str
    conducteur: str
    email_conducteur: str = ""
    telephone_conducteur: str = ""
    passagers: List[TrajetPassager] = []
    ordre: str
    google_maps: str


class OptimiserResult(BaseModel):
    trajets: List[TrajetOut]
    co2_economise_kg: float
    co2_facteur_kg_km: float
    max_passagers: int
    seuil_rallonge: float
    co2_par_voiture: List[Co2Voiture]


class TeamCreate(BaseModel):
    code: str
    name: str
    logo_url: Optional[str] = None


class TeamOut(BaseModel):
    id: int
    code: str
    name: str
    logo_url: Optional[str] = None

    class Config:
        from_attributes = True


class EventCreate(BaseModel):
    team_code: str
    destination: str
    title: Optional[str] = None
    event_date: Optional[datetime.datetime] = None


class EventOut(BaseModel):
    id: int
    team_code: str
    destination: str
    title: Optional[str] = None
    event_date: Optional[datetime.datetime] = None
    created_at: datetime.datetime

    class Config:
        from_attributes = True


# -------------------------------------------------------------------
# 5) HTTP session Google (retries + timeouts)
# -------------------------------------------------------------------
session = requests.Session()
retries = Retry(
    total=REQUESTS_TOTAL_RETRIES,
    connect=REQUESTS_TOTAL_RETRIES,
    read=REQUESTS_TOTAL_RETRIES,
    backoff_factor=REQUESTS_BACKOFF,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST"],
    raise_on_status=False,
)
adapter = HTTPAdapter(max_retries=retries)
session.mount("https://", adapter)
session.mount("http://", adapter)

DEFAULT_TIMEOUT = (CONNECT_TIMEOUT, READ_TIMEOUT)  # (connect, read)


# -------------------------------------------------------------------
# 6) FASTAPI APP + startup
# -------------------------------------------------------------------
app = FastAPI()

origins = [
    "http://localhost:3000",
    "http://88.184.161.151:3000",
    "http://192.168.1.85:3000",
    # plus tard, ton futur domaine frontend :
    "https://sport-cov.fr",
    "https://www.sport-cov.fr",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def check_api_key():
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY manquante (variable d'environnement).")


@app.on_event("startup")
def init_db():
    Base.metadata.create_all(bind=engine)


VERSION = "pdf-template V3 + events/trips persistence (2025-11-18)"


@app.on_event("startup")
def print_version():
    print("### SERVICE VERSION:", VERSION)


# -------------------------------------------------------------------
# 7) Helpers Google
# -------------------------------------------------------------------
@lru_cache(maxsize=1024)
def geocode_address_cached(address: str) -> Tuple[float, float]:
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY manquante.")
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_API_KEY}
    try:
        resp = session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        raise HTTPException(
            status_code=500,
            detail=f"Timeout géocodage pour '{address}'",
        )
    except requests.exceptions.RequestException as e:
        raise HTTPException(
            status_code=500,
            detail=f"Échec appel Google Geocode: {e}",
        )

    data = resp.json()
    status = data.get("status", "UNKNOWN")

    if status == "OK" and data.get("results"):
        loc = data["results"][0]["geometry"]["location"]
        return (loc["lng"], loc["lat"])  # (lng, lat)
    elif status == "ZERO_RESULTS":
        # adresse introuvable côté Google → 400
        raise HTTPException(
            status_code=400,
            detail=f"Adresse introuvable : {address}",
        )
    else:
        # autre erreur Google → 400 aussi (mauvaise requête, clé, quota, etc.)
        raise HTTPException(
            status_code=400,
            detail=f"Geocode error: {status}",
        )

def geocode_address(address: str) -> Tuple[float, float]:
    try:
        lng, lat = geocode_address_cached(address.strip())
        return (lng, lat)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur geocodage '{address}' : {e}")


@lru_cache(maxsize=8192)
def get_google_duration(origin: Tuple[float, float], destination: Tuple[float, float]) -> int:
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{origin[1]},{origin[0]}",
        "destination": f"{destination[1]},{destination[0]}",
        "key": GOOGLE_API_KEY,
        "mode": "driving",
    }
    try:
        response = session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        status = data.get("status")
        if status == "OK":
            return data["routes"][0]["legs"][0]["duration"]["value"]
        raise HTTPException(status_code=400, detail=f"Google Directions error: {status}")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=500, detail="Timeout vers Google Directions")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur Google Directions: {e}")


@lru_cache(maxsize=8192)
def get_google_distance_km(origin: Tuple[float, float], destination: Tuple[float, float]) -> float:
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{origin[1]},{origin[0]}",
        "destination": f"{destination[1]},{destination[0]}",
        "key": GOOGLE_API_KEY,
        "mode": "driving",
    }
    try:
        response = session.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        status = data.get("status")
        if status == "OK":
            meters = data["routes"][0]["legs"][0]["distance"]["value"]
            return meters / 1000.0
        raise HTTPException(status_code=400, detail=f"Google Directions error: {status}")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=500, detail="Timeout vers Google Directions")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Erreur Google Directions: {e}")
    except (KeyError, IndexError):
        raise HTTPException(status_code=500, detail="Réponse Google Directions invalide")


def create_google_maps_link(adresses: List[str]) -> str:
    if len(adresses) < 2:
        return ""
    origin = urllib.parse.quote(adresses[0])
    destination = urllib.parse.quote(adresses[-1])
    waypoints = "|".join(urllib.parse.quote(adr) for adr in adresses[1:-1])
    return f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}&waypoints={waypoints}"


def slugify(value: str) -> str:
    value = value.strip().lower()
    out = []
    for c in value:
        if c.isalnum():
            out.append(c)
        elif c in " -_/":
            out.append("-")
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:50] or "team"

def format_full_address(row: ParticipantORM) -> str:
    """
    Construit une adresse complète et propre pour l'API Google:
    "adresse, code_postal ville, France"
    """
    parts: list[str] = []

    if row.address:
        parts.append(row.address.strip())

    cp_ville = " ".join(
        p.strip()
        for p in [row.postal_code or "", row.city or ""]
        if p and p.strip()
    )
    if cp_ville:
        parts.append(cp_ville)

    # On force le pays pour aider Google
    parts.append("France")

    # On filtre les éléments vides et on joint
    return ", ".join(p for p in parts if p)

# -------------------------------------------------------------------
# 8) Diag
# -------------------------------------------------------------------
@app.get("/_diag/google")
def diag_google():
    try:
        r = session.get("https://maps.googleapis.com/generate_204", timeout=(3, 5))
        return {"ok": True, "status_code": r.status_code}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Egress KO: {e}")


# -------------------------------------------------------------------
# 9) Cœur de l’algo d’optimisation
# -------------------------------------------------------------------
def _run_optimisation(data: InputData) -> dict:
    participants = data.participants
    destination = data.destination

    indexed = list(enumerate(participants))  # [(pid, Participant), ...]

    infos_participants = {
        pid: {
            "name": p.name,
            "email": p.email,
            "telephone": p.telephone,
            "address": p.address,
        }
        for pid, p in indexed
    }

    try:
        coords = {pid: geocode_address(p.address) for pid, p in indexed}
        coord_dest = geocode_address(destination)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur géocodage : {e}")

    try:
        durees_directes = {pid: get_google_duration(coords[pid], coord_dest) for pid, _ in indexed}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de calcul des durées directes : {e}")

    non_assignes = set(pid for pid, _ in indexed)
    trajets: List[dict] = []
    trajets_ids: List[List[int]] = []

    from math import inf

    while non_assignes:
        conducteur = max(non_assignes, key=lambda pid: durees_directes[pid])

        passagers_compatibles: List[int] = []
        for autre in non_assignes:
            if autre == conducteur:
                continue
            duree_aller = get_google_duration(coords[conducteur], coords[autre])
            duree_retour = get_google_duration(coords[autre], coord_dest)
            if (duree_aller + duree_retour) <= SEUIL_RALLONGE * durees_directes[conducteur]:
                passagers_compatibles.append(autre)

        best_subset: List[int] = []
        best_k = -1
        best_duration = inf
        limit = min(MAX_PASSENGERS, len(passagers_compatibles))

        for k in range(limit, -1, -1):
            for subset in combinations(passagers_compatibles, k):
                points = [coords[conducteur]] + [coords[pid] for pid in subset] + [coord_dest]
                duree_trajet = sum(get_google_duration(points[i], points[i + 1]) for i in range(len(points) - 1))
                if duree_trajet > SEUIL_RALLONGE * durees_directes[conducteur]:
                    continue
                if (k > best_k) or (k == best_k and duree_trajet < best_duration):
                    best_k = k
                    best_duration = duree_trajet
                    best_subset = list(subset)

        pids_trajet = [conducteur] + best_subset
        adresses = [infos_participants[pid]["address"] for pid in pids_trajet] + [destination]

        trajets.append(
            {
                "voiture": f"Voiture {len(trajets) + 1}",
                "conducteur": infos_participants[conducteur]["name"],
                "email_conducteur": infos_participants[conducteur]["email"],
                "telephone_conducteur": infos_participants[conducteur]["telephone"],
                "passagers": [
                    {
                        "nom": infos_participants[pid]["name"],
                        "marche": False,
                        "email": infos_participants[pid]["email"],
                        "telephone": infos_participants[pid]["telephone"],
                    }
                    for pid in best_subset
                ],
                "ordre": " → ".join(adresses),
                "google_maps": create_google_maps_link(adresses),
            }
        )
        trajets_ids.append(pids_trajet)
        non_assignes -= set(pids_trajet)

    try:
        co2_par_voiture = []
        for i, t in enumerate(trajets):
            pids_trajet = trajets_ids[i]
            passagers_pids = pids_trajet[1:]
            co2_v = 0.0
            for pid in passagers_pids:
                dist_km = get_google_distance_km(coords[pid], coord_dest)  # aller simple
                co2_v += dist_km * CO2_PER_KM * 2  # A/R
            co2_par_voiture.append({
                "voiture": t["voiture"],
                "conducteur": t["conducteur"],
                "email_conducteur": t["email_conducteur"],
                "nb_passagers": len(passagers_pids),
                "co2_voiture_kg": round(co2_v, 2),
            })
        co2_total_kg = round(sum(v["co2_voiture_kg"] for v in co2_par_voiture), 2)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur calcul CO2 : {e}")

    return {
        "trajets": trajets,
        "co2_economise_kg": co2_total_kg,
        "co2_facteur_kg_km": CO2_PER_KM,
        "max_passagers": MAX_PASSENGERS,
        "seuil_rallonge": SEUIL_RALLONGE,
        "co2_par_voiture": co2_par_voiture,
    }


# -------------------------------------------------------------------
# 10) Endpoints d’optimisation
# -------------------------------------------------------------------
@app.post("/optimiser_direct", response_model=OptimiserResult)
async def optimiser_trajets(data: InputData):
    result_dict = _run_optimisation(data)
    return OptimiserResult(**result_dict)

@app.post("/events/optimize_and_save")
async def optimize_and_save(payload: OptimizeAndSavePayload, db: Session = Depends(get_db)):
    """
    Appelé depuis n8n :
    - crée / retrouve l'équipe (par nom),
    - met à jour les participants de l’équipe,
    - crée l'événement,
    - calcule les trajets,
    - enregistre trips + passagers + CO₂.
    """

    name = payload.team_name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="team_name obligatoire")

    # 1) Récupérer ou créer l'équipe
    team = db.query(TeamORM).filter(TeamORM.name == name).first()
    if not team:
        team = TeamORM(code=slugify(name), name=name)
        db.add(team)
        db.commit()
        db.refresh(team)

    # 2) Mettre à jour la table participants (roster de l’équipe)
    existing = db.query(ParticipantORM).filter(ParticipantORM.team_id == team.id).all()
    existing_index = {
        (p.name.strip().lower(), (p.email or "").strip().lower()): p for p in existing
    }

    for p in payload.participants:
        key = (p.name.strip().lower(), (p.email or "").strip().lower())
        if key in existing_index:
            row = existing_index[key]
            row.address = p.address
            row.email = p.email or ""
            row.telephone = p.telephone or ""
        else:
            row = ParticipantORM(
                team_id=team.id,
                name=p.name,
                address=p.address,
                email=p.email or "",
                telephone=p.telephone or "",
            )
            db.add(row)
            existing_index[key] = row

    db.flush()

    # 3) Créer l'événement
    event = EventORM(
        team_id=team.id,
        title=f"Match à {payload.destination}",
        destination=payload.destination,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    # 4) Calcul des trajets
    input_data = InputData(
        participants=payload.participants,
        destination=payload.destination,
    )
    result = _run_optimisation(input_data)

    trajets = result["trajets"]
    co2_list = result["co2_par_voiture"]

    # Nettoyer d’éventuels anciens trips/CO2 pour cet event
    for trip in list(event.trips):
        db.delete(trip)
    for co2 in list(event.co2_entries):
        db.delete(co2)
    db.flush()

    def find_co2_for_trip(trip_dict: dict) -> float:
        for c in co2_list:
            if (
                c["voiture"] == trip_dict["voiture"]
                and c["email_conducteur"] == trip_dict["email_conducteur"]
            ):
                return c["co2_voiture_kg"]
        return 0.0

    # Créer nouveaux trips / passagers / CO₂
    for t in trajets:
        trip = TripORM(
            event_id=event.id,
            voiture=t["voiture"],
            conducteur=t["conducteur"],
            email_conducteur=t["email_conducteur"],
            telephone_conducteur=t["telephone_conducteur"],
            ordre=t["ordre"],
            google_maps=t["google_maps"],
        )
        db.add(trip)
        db.flush()

        for p in t["passagers"]:
            tp = TripPassengerORM(
                trip_id=trip.id,
                nom=p["nom"],
                marche=p.get("marche", False),
                email=p.get("email", ""),
                telephone=p.get("telephone", ""),
            )
            db.add(tp)

        co2_value = find_co2_for_trip(t)
        tc = TripCO2ORM(
            event_id=event.id,
            voiture=t["voiture"],
            conducteur=t["conducteur"],
            email_conducteur=t["email_conducteur"],
            nb_passagers=len(t["passagers"]),
            co2_voiture_kg=co2_value,
        )
        db.add(tc)

    db.commit()

    return {
        "event_id": event.id,
        "team_id": team.id,
        "nb_trips": len(trajets),
        "co2_economise_kg": result["co2_economise_kg"],
        "trajets": trajets,
        "co2_par_voiture": co2_list,
    }


# -------------------------------------------------------------------

def _require_team_owner(team_id: int, current_user: UserORM, db: Session) -> "TeamORM":
    team = db.query(TeamORM).filter(TeamORM.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Équipe introuvable")
    if not current_user.is_admin and team.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Accès interdit à cette équipe")
    return team

# 11) Endpoints teams / events / trips
# -------------------------------------------------------------------
@app.post("/teams", response_model=TeamOut)
def create_or_update_team(team: TeamCreate, db: Session = Depends(get_db), current_user: UserORM = Depends(get_current_user)):
    existing = db.query(TeamORM).filter(TeamORM.code == team.code, TeamORM.user_id == current_user.id).first()
    if existing:
        existing.name = team.name
        existing.logo_url = team.logo_url
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing
    new_team = TeamORM(code=team.code, name=team.name, logo_url=team.logo_url, user_id=current_user.id)
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    return new_team


@app.get("/teams", response_model=List[TeamOut])
def list_teams(db: Session = Depends(get_db), current_user: UserORM = Depends(get_current_user)):
    if current_user.is_admin:
        teams = db.query(TeamORM).order_by(TeamORM.created_at.desc()).all()
    else:
        teams = db.query(TeamORM).filter(TeamORM.user_id == current_user.id).order_by(TeamORM.created_at.desc()).all()
    return teams


@app.get("/teams/{team_id}/participants", response_model=List[ParticipantOut])
def list_team_participants(team_id: int, db: Session = Depends(get_db), current_user: UserORM = Depends(get_current_user)):
    _require_team_owner(team_id, current_user, db)
    participants = (
        db.query(ParticipantORM)
        .filter(ParticipantORM.team_id == team_id)
        .order_by(ParticipantORM.name.asc())
        .all()
    )
    return participants

@app.post("/teams/{team_id}/participants", response_model=ParticipantOut)
def create_participant(team_id: int, payload: ParticipantCreate, db: Session = Depends(get_db), current_user: UserORM = Depends(get_current_user)):
    team = _require_team_owner(team_id, current_user, db)

    participant = ParticipantORM(
        team_id=team_id,
        name=payload.name.strip(),
        address=payload.address.strip(),
        postal_code=(payload.postal_code or "").strip() or None,
        city=(payload.city or "").strip() or None,
        email=(payload.email or "").strip() or None,
        telephone=(payload.telephone or "").strip() or None,
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


@app.put("/participants/{participant_id}", response_model=ParticipantOut)
def update_participant(participant_id: int, payload: ParticipantUpdate, db: Session = Depends(get_db)):
    participant = db.query(ParticipantORM).filter(ParticipantORM.id == participant_id).first()
    if not participant:
        raise HTTPException(status_code=404, detail=f"Participant {participant_id} introuvable")

    if payload.name is not None:
        participant.name = payload.name.strip()
    if payload.address is not None:
        participant.address = payload.address.strip()
    if payload.postal_code is not None:
        participant.postal_code = payload.postal_code.strip() or None
    if payload.city is not None:
        participant.city = payload.city.strip() or None
    if payload.email is not None:
        participant.email = payload.email.strip() or None
    if payload.telephone is not None:
        participant.telephone = payload.telephone.strip() or None

    db.add(participant)
    db.commit()
    db.refresh(participant)
    return participant


@app.delete("/participants/{participant_id}")
def delete_participant(participant_id: int, db: Session = Depends(get_db)):
    participant = db.query(ParticipantORM).filter(ParticipantORM.id == participant_id).first()
    if not participant:
        raise HTTPException(status_code=404, detail=f"Participant {participant_id} introuvable")

    db.delete(participant)
    db.commit()
    return {"ok": True}

@app.post("/events", response_model=EventOut)
def create_event(payload: EventCreate, db: Session = Depends(get_db)):
    team = db.query(TeamORM).filter(TeamORM.code == payload.team_code).first()
    if not team:
        raise HTTPException(status_code=404, detail=f"Team avec code '{payload.team_code}' introuvable")

    event = EventORM(
        team_id=team.id,
        title=payload.title,
        destination=payload.destination,
        event_date=payload.event_date,
    )
    db.add(event)
    db.commit()
    db.refresh(event)

    return EventOut(
        id=event.id,
        team_code=team.code,
        destination=event.destination,
        title=event.title,
        event_date=event.event_date,
        created_at=event.created_at,
    )


@app.get("/events", response_model=List[EventOut])
def list_events(db: Session = Depends(get_db), current_user: UserORM = Depends(get_current_user)):
    """
    Liste tous les événements avec leur team_code, via une requête SQL brute.
    """
    rows = db.execute(
        text(
            """
            SELECT
              e.id,
              COALESCE(t.code, '') AS team_code,
              e.destination,
              e.title,
              e.event_date,
              e.created_at
            FROM events e
            LEFT JOIN teams t ON e.team_id = t.id
            ORDER BY e.created_at DESC
            """
        )
    ).mappings().all()

    return [
        EventOut(
            id=r["id"],
            team_code=r["team_code"],
            destination=r["destination"],
            title=r["title"],
            event_date=r["event_date"],
            created_at=r["created_at"],
        )
        for r in rows
    ]
def format_full_address(p: ParticipantORM) -> str:
    """
    Construit une adresse complète à partir des champs
    address + postal_code + city, en ajoutant 'France'.
    (équivalent de ce que tu faisais dans n8n.)
    """
    parts: list[str] = []

    if p.address:
        parts.append(p.address.strip())

    cp_ville = " ".join(
        x.strip()
        for x in [p.postal_code or "", p.city or ""]
        if x and x.strip()
    )
    if cp_ville:
        parts.append(cp_ville)

    # tu peux adapter si un jour tu as des clubs hors France
    parts.append("France")

    # On joint avec des virgules pour un format très classique
    return ", ".join(parts)

@app.get("/teams/{team_id}/events", response_model=List[EventOut])
def list_team_events(team_id: int, db: Session = Depends(get_db), current_user: UserORM = Depends(get_current_user)):
    _require_team_owner(team_id, current_user, db)
    """
    Liste uniquement les événements d'une équipe donnée.
    """
    events = (
        db.query(EventORM)
        .filter(EventORM.team_id == team_id)
        .order_by(EventORM.created_at.desc())
        .all()
    )

    return [
        EventOut(
            id=e.id,
            team_code=e.team.code if e.team else "",
            destination=e.destination,
            title=e.title,
            event_date=e.event_date,
            created_at=e.created_at,
        )
        for e in events
    ]


@app.get("/events/{event_id}", response_model=EventOut)
def get_event(event_id: int, db: Session = Depends(get_db)):
    """
    Détail d'un événement (pour la page /events/[id])
    """
    row = db.execute(
        text(
            """
            SELECT
              e.id,
              COALESCE(t.code, '') AS team_code,
              e.destination,
              e.title,
              e.event_date,
              e.created_at
            FROM events e
            LEFT JOIN teams t ON e.team_id = t.id
            WHERE e.id = :event_id
            """
        ),
        {"event_id": event_id},
    ).mappings().first()

    if not row:
        raise HTTPException(status_code=404, detail="Événement introuvable")

    return EventOut(
        id=row["id"],
        team_code=row["team_code"],
        destination=row["destination"],
        title=row["title"],
        event_date=row["event_date"],
        created_at=row["created_at"],
    )

@app.post("/teams/{team_id}/carpool/optimize", response_model=OptimiserResult)
async def optimize_carpool(
    team_id: int,
    payload: CarpoolRequest,
    db: Session = Depends(get_db),
    current_user: UserORM = Depends(get_current_user),
):
    """
    Calcule les trajets de covoiturage pour une équipe donnée, à partir :
    - de l'adresse de l'événement (payload.event_address)
    - des IDs de participants sélectionnés (payload.participant_ids)

    ET enregistre :
    - un EventORM
    - les TripORM / TripPassengerORM
    - les TripCO2ORM
    """

    if not payload.event_address.strip():
        raise HTTPException(status_code=400, detail="Adresse de l’événement obligatoire.")

    if not payload.participant_ids:
        raise HTTPException(status_code=400, detail="Aucun participant sélectionné.")

    # 1) Récupérer les participants en BDD
    participants_rows = (
        db.query(ParticipantORM)
        .filter(ParticipantORM.team_id == team_id)
        .filter(ParticipantORM.id.in_(payload.participant_ids))
        .order_by(ParticipantORM.name.asc())
        .all()
    )

    if not participants_rows:
        raise HTTPException(
            status_code=404,
            detail="Aucun participant trouvé pour cette équipe / ces IDs.",
        )

    # 2) Construire les données pour l’algo
    participants_input: List[Participant] = []
    for row in participants_rows:
        participants_input.append(
            Participant(
                name=row.name,
                address=format_full_address(row),
                email=row.email or "",
                telephone=row.telephone or "",
            )
        )

    input_data = InputData(
        participants=participants_input,
        destination=payload.event_address.strip(),
    )

    # 3) Appeler l’algo d’optimisation
    result_dict = _run_optimisation(input_data)

    # 4) Créer un événement en BDD
    title = (payload.event_title or f"Covoiturage vers {payload.event_address.strip()}").strip()

    event = EventORM(
        team_id=team_id,
        title=title,
        destination=payload.event_address.strip(),
        event_date=None,  # on gèrera la date plus tard
    )
    db.add(event)
    db.flush()  # pour avoir event.id

    trajets = result_dict["trajets"]
    co2_list = result_dict["co2_par_voiture"]

    def find_co2_for_trip(trip_dict: dict) -> float:
        for c in co2_list:
            if (
                c["voiture"] == trip_dict["voiture"]
                and c["email_conducteur"] == trip_dict["email_conducteur"]
            ):
                return c["co2_voiture_kg"]
        return 0.0

    # 5) Enregistrer trips + passagers + CO2
    for t in trajets:
        trip = TripORM(
            event_id=event.id,
            voiture=t["voiture"],
            conducteur=t["conducteur"],
            email_conducteur=t["email_conducteur"],
            telephone_conducteur=t["telephone_conducteur"],
            ordre=t["ordre"],
            google_maps=t["google_maps"],
        )
        db.add(trip)
        db.flush()

        # Passagers
        for p in t["passagers"]:
            passenger = TripPassengerORM(
                trip_id=trip.id,
                nom=p["nom"],
                marche=p.get("marche", False),
                email=p.get("email", ""),
                telephone=p.get("telephone", ""),
            )
            db.add(passenger)

        # CO₂ pour ce trajet
        co2_value = find_co2_for_trip(t)
        co2_row = TripCO2ORM(
            event_id=event.id,
            voiture=t["voiture"],
            conducteur=t["conducteur"],
            email_conducteur=t["email_conducteur"],
            nb_passagers=len(t["passagers"]),
            co2_voiture_kg=co2_value,
        )
        db.add(co2_row)

    db.commit()

    # 6) On renvoie toujours le même format que avant
    return OptimiserResult(**result_dict)

@app.post("/events/{event_id}/recompute", response_model=OptimiserResult)
async def recompute_event(event_id: int, data: InputData, db: Session = Depends(get_db)):
    event = db.query(EventORM).filter(EventORM.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail=f"Événement {event_id} introuvable")

    if not data.destination.strip():
        data = InputData(participants=data.participants, destination=event.destination)
    else:
        if data.destination != event.destination:
            event.destination = data.destination
            db.add(event)
            db.flush()

    result_dict = _run_optimisation(data)

    for trip in list(event.trips):
        db.delete(trip)
    for co2 in list(event.co2_entries):
        db.delete(co2)
    db.flush()

    trajets = result_dict["trajets"]
    for t in trajets:
        trip = TripORM(
            event=event,
            voiture=t["voiture"],
            conducteur=t["conducteur"],
            email_conducteur=t["email_conducteur"],
            telephone_conducteur=t["telephone_conducteur"],
            ordre=t["ordre"],
            google_maps=t["google_maps"],
        )
        db.add(trip)
        db.flush()

        for p in t["passagers"]:
            passenger = TripPassengerORM(
                trip=trip,
                nom=p["nom"],
                marche=p.get("marche", False),
                email=p.get("email", ""),
                telephone=p.get("telephone", ""),
            )
            db.add(passenger)

    for v in result_dict["co2_par_voiture"]:
        co2_row = TripCO2ORM(
            event=event,
            voiture=v["voiture"],
            conducteur=v["conducteur"],
            email_conducteur=v["email_conducteur"],
            nb_passagers=v["nb_passagers"],
            co2_voiture_kg=v["co2_voiture_kg"],
        )
        db.add(co2_row)

    db.commit()

    return OptimiserResult(**result_dict)


@app.get("/events/{event_id}/trips", response_model=OptimiserResult)
def get_event_trips(event_id: int, db: Session = Depends(get_db), _: UserORM = Depends(get_current_user)):
    event = db.query(EventORM).filter(EventORM.id == event_id).first()
    if not event:
        raise HTTPException(status_code=404, detail=f"Événement {event_id} introuvable")

    trajets: List[TrajetOut] = []
    for trip in event.trips:
        passengers = [
            TrajetPassager(
                nom=p.nom,
                marche=p.marche,
                email=p.email or "",
                telephone=p.telephone or "",
            )
            for p in trip.passengers
        ]
        trajets.append(
            TrajetOut(
                voiture=trip.voiture,
                conducteur=trip.conducteur,
                email_conducteur=trip.email_conducteur or "",
                telephone_conducteur=trip.telephone_conducteur or "",
                passagers=passengers,
                ordre=trip.ordre,
                google_maps=trip.google_maps,
            )
        )

    co2_par_voiture: List[Co2Voiture] = [
        Co2Voiture(
            voiture=row.voiture,
            conducteur=row.conducteur,
            email_conducteur=row.email_conducteur or "",
            nb_passagers=row.nb_passagers,
            co2_voiture_kg=row.co2_voiture_kg,
        )
        for row in event.co2_entries
    ]

    co2_total_kg = round(sum(r.co2_voiture_kg for r in co2_par_voiture), 2)

    return OptimiserResult(
        trajets=trajets,
        co2_economise_kg=co2_total_kg,
        co2_facteur_kg_km=CO2_PER_KM,
        max_passagers=MAX_PASSENGERS,
        seuil_rallonge=SEUIL_RALLONGE,
        co2_par_voiture=co2_par_voiture,
    )


# -------------------------------------------------------------------
# 12) PDF
# -------------------------------------------------------------------
PDF_CSS = """
@page { size: A4; margin: 18mm; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; font-size: 12pt; }
h1 { font-size: 22pt; margin: 0 0 12px 0; }
h2 { font-size: 14pt; margin: 18px 0 6px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }

.car { break-inside: avoid; page-break-inside: avoid; margin-bottom: 8mm; }
.car h2 { break-after: avoid; page-break-after: avoid; }

.table, .table tr, .table td, .table th { break-inside: avoid; page-break-inside: avoid; }

.table { width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 10pt; line-height: 1.2; }
.table th, .table td { border: 1px solid #ccc; padding: 4px 6px; vertical-align: top; }

.badge { display: inline-block; padding: 2px 8px; border-radius: 12px; border: 1px solid #888; font-size: 10pt; }
.small { color: #666; font-size: 10pt; }
a { color: #0645AD; word-break: break-all; }
.footer { margin-top: 16px; font-size: 10pt; color: #666; }
.header { display:flex; align-items:center; gap:12px; margin-bottom: 8px; }
.header img { height: 36px; }
"""

PDF_TEMPLATE = Template(r"""
<!doctype html>
<html lang="fr">
  <head>
    <meta charset="utf-8">
    <style>
      .header { display:flex; align-items:flex-start; gap:12px; margin-bottom:8px; }
      .logo { flex:0 0 auto; }
      .logo img { height:30mm !important; width:auto; display:block; }
    </style>
  </head>
  <body>
    <div class="header">
      {% if logo_url %}<div class="logo"><img src="{{ logo_url }}" alt="logo"></div>{% endif %}
      <div class="title">
        <h1>{{ team_name or "Mon équipe" }} — Covoiturage </h1>
        <div class="small">Généré le {{ now }}</div>
        <br>
        {% if destination %}<div class="small">Destination : <strong>{{ destination }}</strong></div>{% endif %}
      </div>
    </div>

    <h1>Détail des trajets optimisés</h1>
    {% for t in trajets %}
      <div class="car">
        <h2>{{ t.voiture }}</h2>
        <table class="table">
          <tr>
            <th style="width:28%">Conducteur</th>
            <td>{{ t.conducteur }}</td>
          </tr>
          <tr>
            <th>Passagers</th>
            <td>
              {% if t.passagers %}
                {% for p in t.passagers %}
                  • {{ p.nom }}{% if p.marche %} <span class="badge">à pied</span>{% endif %}<br>
                {% endfor %}
              {% else %}
                Aucun passager
              {% endif %}
            </td>
          </tr>
          <tr>
            <th>Itinéraire (lien Google Maps)</th>
            <td><a href="{{ t.google_maps }}">{{ t.ordre }}</a></td>
          </tr>
        </table>
      </div>
    {% endfor %}
    <br><br>

    <h1>Économie de CO² par voiture</h1>
    <table class="table">
      <thead><tr><th>Voiture</th><th>Conducteur</th><th>Passagers</th><th>CO₂ économisé (kg)</th></tr></thead>
      <tbody>
      {% for v in co2_par_voiture %}
        <tr>
          <td>{{ v.voiture }}</td>
          <td>{{ v.conducteur }}</td>
          <td>{{ v.nb_passagers }}</td>
          <td>{{ "%.2f"|format(v.co2_voiture_kg) }}</td>
        </tr>
      {% endfor %}
      <tr>
        <td colspan="3" style="text-align:right;"><strong>Total</strong></td>
        <td><strong>{{ "%.2f"|format(co2_total) }}</strong></td>
      </tr>
      </tbody>
    </table>

    <div class="footer">
      Facteur CO₂: {{ co2_facteur }} kg/km
    </div>
  </body>
</html>
""")


@app.post("/export_pdf")
async def export_pdf(data: InputData, club_name: str = "Sport Cov", logo_url: str = ""):
    logo = (logo_url or LOGO_URL_DEFAULT).strip()
    result = _run_optimisation(data)
    html_str = PDF_TEMPLATE.render(
        now=datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        club_name=club_name,
        team_name=None,
        destination=data.destination,
        logo_url=logo,
        trajets=result["trajets"],
        co2_par_voiture=result["co2_par_voiture"],
        co2_total=result["co2_economise_kg"],
        co2_facteur=result["co2_facteur_kg_km"],
        max_passagers=result["max_passagers"],
        seuil_rallonge=result["seuil_rallonge"],
    )
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    HTML(string=html_str).write_pdf(tmp.name, stylesheets=[CSS(string=PDF_CSS)])
    return FileResponse(tmp.name, media_type="application/pdf", filename="Mon_equipe_covoiturage.pdf")


@app.post("/export_pdf_from_result")
async def export_pdf_from_result(
    result: OptimiserResult,
    club_name: str = "Sport Cov",
    logo_url: str = "",
    team_name: str = "",
    destination: str = "",
):
    html_str = PDF_TEMPLATE.render(
        now=datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        club_name=club_name,
        team_name=team_name,
        destination=destination,
        logo_url=(logo_url or LOGO_URL_DEFAULT),
        trajets=[t.dict() for t in result.trajets],
        co2_par_voiture=[v.dict() for v in result.co2_par_voiture],
        co2_total=result.co2_economise_kg,
        co2_facteur=result.co2_facteur_kg_km,
        max_passagers=result.max_passagers,
        seuil_rallonge=result.seuil_rallonge,
    )
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    HTML(string=html_str).write_pdf(tmp.name, stylesheets=[CSS(string=PDF_CSS)])
    return FileResponse(tmp.name, media_type="application/pdf", filename="Mon_equipe_covoiturage.pdf")


@app.get("/_version")
def _version():
    git = os.getenv("RENDER_GIT_COMMIT", "") or os.getenv("COMMIT", "")
    branch = os.getenv("RENDER_GIT_BRANCH", "")
    return {"version": VERSION, "git": git, "branch": branch}


# ── Auth ─────────────────────────────────────────────────────────
app.include_router(auth_router)



# ── WebSockets : localisation temps réel + chat par voiture ──────

from fastapi import WebSocket, WebSocketDisconnect
import asyncio, json
from collections import defaultdict

# { "eventId_voiture" -> {"driver": ws|None, "passengers": [ws,...], "location": dict|None} }
_loc_rooms: dict = defaultdict(lambda: {"driver": None, "passengers": [], "location": None})

# { "eventId_voiture" -> [{"nom": str, "msg": str}, ...] }
_chat_rooms: dict = defaultdict(list)

# { "eventId_voiture" -> [ws, ...] }
_chat_connections: dict = defaultdict(list)


@app.websocket("/ws/location/{event_id}/{voiture}")
async def ws_location(ws: WebSocket, event_id: int, voiture: str, role: str = "passenger"):
    await ws.accept()
    key = f"{event_id}_{voiture}"
    room = _loc_rooms[key]

    if role == "driver":
        room["driver"] = ws
        try:
            while True:
                data = await ws.receive_text()
                loc = json.loads(data)
                room["location"] = loc
                dead = []
                for pws in room["passengers"]:
                    try:
                        await pws.send_text(data)
                    except Exception:
                        dead.append(pws)
                for d in dead:
                    room["passengers"].remove(d)
        except WebSocketDisconnect:
            room["driver"] = None
    else:
        room["passengers"].append(ws)
        if room["location"]:
            await ws.send_text(json.dumps(room["location"]))
        try:
            while True:
                await asyncio.sleep(30)
                await ws.send_text(json.dumps({"ping": True}))
        except WebSocketDisconnect:
            if ws in room["passengers"]:
                room["passengers"].remove(ws)


@app.websocket("/ws/chat/{event_id}/{voiture}")
async def ws_chat(ws: WebSocket, event_id: int, voiture: str):
    await ws.accept()
    key = f"{event_id}_{voiture}"
    _chat_connections[key].append(ws)

    # Envoyer l'historique
    for msg in _chat_rooms[key]:
        await ws.send_text(json.dumps(msg))

    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            _chat_rooms[key].append(msg)
            dead = []
            for cws in _chat_connections[key]:
                try:
                    await cws.send_text(json.dumps(msg))
                except Exception:
                    dead.append(cws)
            for d in dead:
                _chat_connections[key].remove(d)
    except WebSocketDisconnect:
        if ws in _chat_connections[key]:
            _chat_connections[key].remove(ws)


@app.get("/events/{event_id}/trips/player/{token}")
def get_player_trip(event_id: int, token: str, db: Session = Depends(get_db)):
    """Retourne le trajet d'un joueur via son token unique."""
    participant = db.query(ParticipantORM).filter(ParticipantORM.token == token).first()
    if not participant:
        raise HTTPException(status_code=404, detail="Lien invalide")

    event = db.query(EventORM).filter(EventORM.id == event_id).first()
    if not event or event.team_id != participant.team_id:
        raise HTTPException(status_code=404, detail="Événement introuvable pour ce participant")

    trips = db.query(TripORM).filter(TripORM.event_id == event_id).all()
    nom_lower = participant.name.strip().lower()

    for trip in trips:
        if trip.conducteur.strip().lower() == nom_lower:
            result = _trip_to_dict(trip, role="driver")
            result["player_name"] = participant.name
            return result
        for p in trip.passengers:
            if p.nom.strip().lower() == nom_lower:
                result = _trip_to_dict(trip, role="passenger")
                result["player_name"] = participant.name
                return result

    raise HTTPException(status_code=404, detail="Participant non trouvé dans cet événement")


def _trip_to_dict(trip: "TripORM", role: str) -> dict:
    return {
        "voiture": trip.voiture,
        "role": role,
        "conducteur": trip.conducteur,
        "telephone_conducteur": trip.telephone_conducteur or "",
        "passagers": [
            {"nom": p.nom, "telephone": p.telephone or "", "marche": p.marche}
            for p in trip.passengers
        ],
        "google_maps": trip.google_maps,
        "ordre": trip.ordre,
    }
