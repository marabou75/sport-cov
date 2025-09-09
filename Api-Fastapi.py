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

# Seuil de rallonge (par défaut 1.5)
SEUIL_RALLONGE = float(os.getenv("SEUIL_RALLONGE", "1.5"))

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

    # Géocodage + durées directes
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

    while non_assignes:
        # Conducteur = le plus loin en durée
        conducteur = max(non_assignes, key=lambda n: durees_directes[n])

        # Passagers compatibles selon rallonge du conducteur
        passagers_compatibles = []
        for autre in non_assignes:
            if autre == conducteur:
                continue
            duree_aller = get_google_duration(coords[conducteur], coords[autre])
            duree_retour = get_google_duration(coords[autre], coord_dest)
            if (duree_aller + duree_retour) <= SEUIL_RALLONGE * durees_directes[conducteur]:
                passagers_compatibles.append(autre)

        # Meilleure combinaison (≤ MAX_PASSENGERS) + garde-fou durée totale
        best_subset: List[str] = []
        best_k = -1
        best_duration = float("inf")
        limit = min(MAX_PASSENGERS, len(passagers_compatibles))

        for k in range(limit, -1, -1):
            for subset in combinations(passagers_compatibles, k):
                points = [coords[conducteur]] + [coords[p] for p in subset] + [coord_dest]
                duree_trajet = sum(get_google_duration(points[i], points[i + 1]) for i in range(len(points) - 1))

                # Garde-fou : trajet final du conducteur ≤ SEUIL_RALLONGE × trajet direct
                if duree_trajet > SEUIL_RALLONGE * durees_directes[conducteur]:
                    continue

                if (k > best_k) or (k == best_k and duree_trajet < best_duration):
                    best_k = k
                    best_duration = duree_trajet
                    best_subset = list(subset)

        # Construire le trajet et retirer les assignés
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

    # ---- CO2 économisé : par voiture + total (passagers uniquement, A/R) ----
    try:
        co2_par_voiture = []

        for t in trajets:
            passagers = t.get("passagers", [])
            co2_v = 0.0

            for pp in passagers:
                nom = pp.get("nom")
                if not nom or nom not in coords:
                    continue
                dist_km = get_google_distance_km(coords[nom], coord_dest)  # aller simple
                co2_v += dist_km * CO2_PER_KM * 2  # A/R

            co2_par_voiture.append({
                "voiture": t.get("voiture", ""),
                "conducteur": t.get("conducteur", ""),
                "email_conducteur": t.get("email_conducteur", ""),
                "nb_passagers": len(passagers),
                "co2_voiture_kg": round(co2_v, 2),
            })

        # total = somme des voitures (équivalent à la somme des passagers)
        co2_total_kg = round(sum(v["co2_voiture_kg"] for v in co2_par_voiture), 2)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur calcul CO2 : {e}")


