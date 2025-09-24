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
