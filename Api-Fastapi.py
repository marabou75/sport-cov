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

# Facteur CO2 moyen (kg / km). Modifiable via env.
CO2_PER_KM = float(os.getenv("CO2_PER_KM", "0.2"))

# Limite de passagers par voiture (par défaut 3)
MAX_PASSENGERS = int(os.getenv("MAX_PASSENGERS", "3"))

# Coefficient de “rallonge” acceptable (max multiplicateur de durée pour le conducteur)
SEUIL_RALLONGE = float(os.getenv("SEUIL_RALLONGE", "1.8"))

app = FastAPI()

@app.on_event("startup")
def check_api_key():
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY manquante (variable d'environnement).")

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
@lru_cache(maxsize=128)
def geocode_address_cached(address: str) -> Tuple[float, float]:
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY manquante.")
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_API_KEY}
    try:
        resp = requests.get(url, params=params, timeout=8)
        resp.raise_for_status()
    except requests.Timeout:
        raise HTTPException(status_code=504, detail=f"Timeout géocodage pour '{address}'")
    except requests.RequestException as e:
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

@lru_cache(maxsize=256)
def get_google_duration(origin: Tuple[float, float], destination: Tuple[float, float]) -> int:
    """Durée (en secondes) entre 2 points (lng, lat)."""
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{origin[1]},{origin[0]}",
        "destination": f"{destination[1]},{destination[0]}",
        "key": GOOGLE_API_KEY,
    }
    response = requests.get(url, params=params, timeout=8)
    response.raise_for_status()
    data = response.json()
    if data["status"] == "OK":
        return data["routes"][0]["legs"][0]["duration"]["value"]
    else:
        raise Exception(f"Google Directions error: {data['status']}")

@lru_cache(maxsize=256)
def get_google_distance_km(origin: Tuple[float, float], destination: Tuple[float, float]) -> float:
    """Distance (en km) entre 2 points (lng, lat)."""
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{origin[1]},{origin[0]}",
        "destination": f"{destination[1]},{destination[0]}",
        "key": GOOGLE_API_KEY,
    }
    response = requests.get(url, params=params, timeout=8)
    response.raise_for_status()
    data = response.json()
    if data["status"] == "OK":
        meters = data["routes"][0]["legs"][0]["distance"]["value"]
        return meters / 1000.0
    else:
        raise Exception(f"Google Directions error: {data['status']}")

def create_google_maps_link(adresses: List[str]) -> str:
    if len(adresses) < 2:
        return ""
    origin = urllib.parse.quote(adresses[0])
    destination = urllib.parse.quote(adresses[-1])
    waypoints = "|".join(urllib.parse.quote(adr) for adr in adresses[1:-1])
    return f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}&waypoints={waypoints}"

# ---- Endpoint principal ----
@app.post("/optimiser_direct")
async def optimiser_trajets(data: InputData):
    participants = data.participants
    infos_participants = {
        p.name: {"email": p.email, "telephone": p.telephone, "address": p.address}
        for p in participants
    }
    destination = data.destination

    # 1) Géocodage + durées directes
    try:
        coords = {p.name: geocode_address(p.address) for p in participants}
        coord_dest = geocode_address(destination)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur géocodage : {e}")

    try:
        durees_directes = {p.name: get_google_duration(coords[p.name], coord_dest) for p in participants}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de calcul des durées directes : {e}")

    non_assignes = set(p.name for p in participants)
    trajets: List[dict] = []

    # 2) Tant qu'il reste des non assignés
    while non_assignes:
        # a) Conducteur = le plus loin (en durée) de la destination
        conducteur = max(non_assignes, key=lambda n: durees_directes[n])

        # b) Passagers compatibles individuellement pour ce conducteur
        passagers_compatibles = []
        for autre in non_assignes:
            if autre == conducteur:
                continue
            duree_aller = get_google_duration(coords[conducteur], coords[autre])
            duree_retour = get_google_duration(coords[autre], coord_dest)
            if (duree_aller + duree_retour) <= SEUIL_RALLONGE * durees_directes[conducteur]:
                passagers_compatibles.append(autre)

        # c) Meilleure combinaison (≤ MAX_PASSENGERS) en respectant le garde-fou global 1.8×
        best_subset = []
        best_k = -1
        best_duration = float("inf")
        limit = min(MAX_PASSENGERS, len(passagers_compatibles))

        for k in range(limit, -1, -1):  # privilégier plus de passagers
            for subset in combinations(passagers_compatibles, k):
                # Trajet complet: conducteur -> passagers (dans cet ordre) -> destination
                points = [coords[conducteur]] + [coords[p] for p in subset] + [coord_dest]
                duree_trajet = sum(
                    get_google_duration(points[i], points[i + 1]) for i in range(len(points) - 1)
                )

                # Garde-fou: la durée finale ne doit pas dépasser SEUIL_RALLONGE × direct
                if duree_trajet > SEUIL_RALLONGE * durees_directes[conducteur]:
                    continue

                # Priorité: (1) plus de passagers ; (2) durée la plus courte
                if (k > best_k) or (k == best_k and duree_trajet < best_duration):
                    best_k = k
                    best_duration = duree_trajet
                    best_subset = list(subset)

        # d) Construire le trajet et retirer les assignés
        noms = [conducteur] + best_subset
        adresses = [infos_participants[n]["address"] for n in noms] + [destination]

        trajets.append(
            {
                "voiture": f"Voiture {len(trajets) + 1}",
                "conducteur": conducteur,
                "email_conducteur": infos_participants[conducteur]["email"],
                "telephone_conducteur": infos_participants[conducteur]["telephone"],
                "passagers": [
                    {
                        "nom": p,
                        "marche": False,
                        "email": infos_participants[p]["email"],
                        "telephone": infos_participants[p]["telephone"],
                    }
                    for p in best_subset
                ],
                "ordre": " → ".join(adresses),
                "google_maps": create_google_maps_link(adresses),
            }
        )

        non_assignes -= set(noms)

    # 3) CO2 économisé par les PASSAGERS uniquement (A/R)
    try:
        noms_passagers = [pp["nom"] for t in trajets for pp in t.get("passagers", [])]
        co2_total_kg = 0.0
        for nom in noms_passagers:
            dist_km = get_google_distance_km(coords[nom], coord_dest)  # aller simple
            co2_total_kg += dist_km * CO2_PER_KM * 2  # A/R
        co2_total_kg = round(co2_total_kg, 2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur calcul CO2 : {e}")

    return {
        "trajets": trajets,
        "co2_economise_kg": co2_total_kg,
        "co2_facteur_kg_km": CO2_PER_KM,
        "max_passagers": MAX_PASSENGERS,
        "seuil_rallonge": SEUIL_RALLONGE,
    }

