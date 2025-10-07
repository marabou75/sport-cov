# main.py
from typing import Tuple, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import urllib.parse
import requests
import os
from dotenv import load_dotenv
from functools import lru_cache
from itertools import combinations

# ---- Config & constantes ----
load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

CO2_PER_KM = float(os.getenv("CO2_PER_KM", "0.2"))            # kg/km
MAX_PASSENGERS = int(os.getenv("MAX_PASSENGERS", "3"))        # passagers max
SEUIL_RALLONGE = float(os.getenv("SEUIL_RALLONGE", "1.5"))    # facteur x trajet direct

LOGO_URL_DEFAULT = os.getenv("LOGO_URL", "").strip()

# Timeouts & retries (surchargeables via env)
CONNECT_TIMEOUT = float(os.getenv("CONNECT_TIMEOUT", "5.0"))
READ_TIMEOUT = float(os.getenv("READ_TIMEOUT", "30.0"))
REQUESTS_TOTAL_RETRIES = int(os.getenv("REQUESTS_TOTAL_RETRIES", "5"))
REQUESTS_BACKOFF = float(os.getenv("REQUESTS_BACKOFF", "0.7"))

app = FastAPI()

@app.on_event("startup")
def check_api_key():
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY manquante (variable d'environnement).")

# ---- Session HTTP robuste (retries + backoff) ----
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

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

# ---- Modèles ----
class Participant(BaseModel):
    name: str
    address: str
    email: str = ""
    telephone: str = ""

class InputData(BaseModel):
    participants: List[Participant]
    destination: str

# --- Modèles "sortie" pour export_pdf_from_result (pas d'appels Google) ---
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


# ---- Helpers Google ----
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
        raise HTTPException(status_code=504, detail=f"Timeout géocodage pour '{address}'")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Échec appel Google Geocode: {e}")
    data = resp.json()
    status = data.get("status", "UNKNOWN")
    if status == "OK" and data.get("results"):
        loc = data["results"][0]["geometry"]["location"]
        return (loc["lng"], loc["lat"])  # (lng, lat)
    elif status == "ZERO_RESULTS":
        raise HTTPException(status_code=400, detail=f"Adresse introuvable : {address}")
    else:
        raise HTTPException(status_code=502, detail=f"Geocode error: {status}")

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
        raise HTTPException(status_code=502, detail=f"Google Directions error: {status}")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Timeout vers Google Directions")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erreur Google Directions: {e}")
    except (KeyError, IndexError):
        raise HTTPException(status_code=502, detail="Réponse Google Directions invalide")

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
        raise HTTPException(status_code=502, detail=f"Google Directions error: {status}")
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="Timeout vers Google Directions")
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Erreur Google Directions: {e}")
    except (KeyError, IndexError):
        raise HTTPException(status_code=502, detail="Réponse Google Directions invalide")

def create_google_maps_link(adresses: List[str]) -> str:
    if len(adresses) < 2:
        return ""
    origin = urllib.parse.quote(adresses[0])
    destination = urllib.parse.quote(adresses[-1])
    waypoints = "|".join(urllib.parse.quote(adr) for adr in adresses[1:-1])
    return f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}&waypoints={waypoints}"

# ---- Endpoint diag ----
@app.get("/_diag/google")
def diag_google():
    try:
        r = session.get("https://maps.googleapis.com/generate_204", timeout=(3, 5))
        return {"ok": True, "status_code": r.status_code}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Egress KO: {e}")

# ---- Endpoint principal (IDs internes) ----
@app.post("/optimiser_direct")
async def optimiser_trajets(data: InputData):
    participants = data.participants
    destination = data.destination

    # IDs internes stables (pid = index)
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

    # Géocodage
    try:
        coords = {pid: geocode_address(p.address) for pid, p in indexed}
        coord_dest = geocode_address(destination)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur géocodage : {e}")

    # Durées directes
    try:
        durees_directes = {pid: get_google_duration(coords[pid], coord_dest) for pid, _ in indexed}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de calcul des durées directes : {e}")

    non_assignes = set(pid for pid, _ in indexed)
    trajets: List[dict] = []
    trajets_ids: List[List[int]] = []

    while non_assignes:
        # Conducteur = celui avec la plus grande durée directe
        conducteur = max(non_assignes, key=lambda pid: durees_directes[pid])

        # Passagers compatibles selon rallonge du conducteur
        passagers_compatibles: List[int] = []
        for autre in non_assignes:
            if autre == conducteur:
                continue
            duree_aller = get_google_duration(coords[conducteur], coords[autre])
            duree_retour = get_google_duration(coords[autre], coord_dest)
            if (duree_aller + duree_retour) <= SEUIL_RALLONGE * durees_directes[conducteur]:
                passagers_compatibles.append(autre)

        # Meilleure combinaison (≤ MAX_PASSENGERS) + garde-fou durée totale
        best_subset: List[int] = []
        best_k = -1
        best_duration = float("inf")
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

        # Construire le trajet
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

    # ---- CO2 économisé : par voiture + total ----
    try:
        co2_par_voiture = []
        for i, t in enumerate(trajets):
            pids_trajet = trajets_ids[i]
            passagers_pids = pids_trajet[1:]  # exclut le conducteur
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

    # ---- ✅ RÉPONSE ----
    return {
        "trajets": trajets,
        "co2_economise_kg": co2_total_kg,
        "co2_facteur_kg_km": CO2_PER_KM,
        "max_passagers": MAX_PASSENGERS,
        "seuil_rallonge": SEUIL_RALLONGE,
        "co2_par_voiture": co2_par_voiture,
    }

# --- Export PDF (basé sur optimiser_trajets) ---
from fastapi.responses import FileResponse
from jinja2 import Template
from weasyprint import HTML, CSS
import tempfile
import datetime

PDF_CSS = """
@page { size: A4; margin: 18mm; }
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; font-size: 12pt; }
h1 { font-size: 22pt; margin: 0 0 12px 0; }
h2 { font-size: 14pt; margin: 18px 0 6px; border-bottom: 1px solid #ddd; padding-bottom: 4px; }
.table { width: 100%; border-collapse: collapse; margin-top: 6px; }
.table th, .table td { border: 1px solid #ccc; padding: 6px 8px; vertical-align: top; }
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
        <h1>{{ team_name or "Mon équipe" }} — Covoiturage V3</h1>
        <div class="small">Généré le {{ now }}</div>
        {% if destination %}<div class="small">Destination : <strong>{{ destination }}</strong></div>{% endif %}
      </div>
    </div>

    <h1>Détail des trajets optimisés</h1>
    {% for t in trajets %}
      <h2>{{ t.voiture }}</h2>
      <table class="table">
        <tr>
          <th style="width:28%">Conducteur</th>
          <td>{{ t.conducteur }}{% if t.telephone_conducteur %}</td>
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
    {% endfor %}

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
    # 1) Réutilise ton algo
    result = await optimiser_trajets(data)
    # 2) Prépare le HTML via Jinja2
    html_str = PDF_TEMPLATE.render(
        now=datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        club_name=club_name,
        logo_url=logo_url,
        trajets=result["trajets"],
        co2_par_voiture=result["co2_par_voiture"],
        co2_total=result["co2_economise_kg"],
        co2_facteur=result["co2_facteur_kg_km"],
        max_passagers=result["max_passagers"],
        seuil_rallonge=result["seuil_rallonge"],
    )
    # 3) HTML -> PDF
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
    """Génère le PDF à partir du JSON déjà calculé par /optimiser_direct (aucun appel Google)."""
    html_str = PDF_TEMPLATE.render(
        now=datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
        club_name=club_name,
        team_name=team_name,
        destination=destination,
        logo_url=logo_url or LOGO_URL_DEFAULT,
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

