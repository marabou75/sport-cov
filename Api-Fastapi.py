from typing import Tuple, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import urllib.parse
import requests
import os
from dotenv import load_dotenv
from functools import lru_cache
from itertools import combinations  # ← NEW

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# === CO2: facteur moyen en kg/km (modifiable via env) ===
CO2_PER_KM = float(os.getenv("CO2_PER_KM", "0.2"))

# === Capacité: max passagers par voiture (hors conducteur) ===
MAX_PASSENGERS = int(os.getenv("MAX_PASSENGERS", "3"))  # ← NEW

app = FastAPI()

@app.on_event("startup")
def check_api_key():
    if not GOOGLE_API_KEY:
        raise RuntimeError("GOOGLE_API_KEY manquante (variable d'environnement).")

class Participant(BaseModel):
    name: str
    address: str
    email: str = ""
    telephone: str = ""

class InputData(BaseModel):
    participants: List[Participant]
    destination: str

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
    """Retourne la durée (en secondes) entre 2 points (lng, lat)."""
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{origin[1]},{origin[0]}",
        "destination": f"{destination[1]},{destination[0]}",
        "key": GOOGLE_API_KEY
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
    """Retourne la distance (en km) entre 2 points (lng, lat)."""
    url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{origin[1]},{origin[0]}",
        "destination": f"{destination[1]},{destination[0]}",
        "key": GOOGLE_API_KEY
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

@app.post("/optimiser_direct")
async def optimiser_trajets(data: InputData):
    participants = data.participants
    infos_participants = {p.name: {"email": p.email, "telephone": p.telephone, "address": p.address} for p in participants}
    destination = data.destination

    try:
        coords = {p.name: geocode_address(p.address) for p in participants}
        coord_dest = geocode_address(destination)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur géocodage : {e}")

    try:
        durees_directes = {
            p.name: get_google_duration(coords[p.name], coord_dest) for p in participants
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur de calcul des durées directes : {e}")

    seuil_rallonge = 2.3
    non_assignes = set(p.name for p in participants)
    trajets = []

    while non_assignes:
        meilleur_scenario = None
        duree_min = float('inf')

        for conducteur_candidat in list(non_assignes):
            try:
                # 1) Qui est "compatible" avec ce conducteur selon la rallonge
                passagers_compatibles = []
                for autre in non_assignes:
                    if autre == conducteur_candidat:
                        continue
                    duree_aller = get_google_duration(coords[conducteur_candidat], coords[autre])
                    duree_retour = get_google_duration(coords[autre], coord_dest)
                    duree_total = duree_aller + duree_retour
                    if duree_total <= seuil_rallonge * durees_directes[conducteur_candidat]:
                        passagers_compatibles.append(autre)

                # 2) On construit un "groupe" large et on teste chaque membre comme conducteur
                groupe = [conducteur_candidat] + passagers_compatibles

                for conducteur in groupe:
                    others = [p for p in groupe if p != conducteur]

                    # 3) ***CONTRAINTE CAPACITÉ*** : tester toutes les combinaisons
                    #    de 0..MAX_PASSENGERS passagers, et prendre la plus rapide
                    limit = min(MAX_PASSENGERS, len(others))
                    for k in range(limit, -1, -1):  # on peut commencer par les plus grands groupes
                        for subset in combinations(others, k):
                            points = [coords[conducteur]] + [coords[p] for p in subset] + [coord_dest]
                            duree_trajet = sum(
                                get_google_duration(points[i], points[i+1]) for i in range(len(points)-1)
                            )
                            if duree_trajet < duree_min:
                                duree_min = duree_trajet
                                meilleur_scenario = {
                                    "conducteur": conducteur,
                                    "passagers": list(subset)  # max 3
                                }

            except Exception:
                continue

        if not meilleur_scenario:
            seul = non_assignes.pop()
            adresse = infos_participants[seul]["address"]
            trajets.append({
                "voiture": f"Voiture {len(trajets)+1}",
                "conducteur": seul,
                "email_conducteur": infos_participants[seul]["email"],
                "telephone_conducteur": infos_participants[seul]["telephone"],
                "passagers": [],
                "ordre": f"{adresse} → {destination}",
                "google_maps": create_google_maps_link([adresse, destination])
            })
        else:
            conducteur = meilleur_scenario["conducteur"]
            passagers = meilleur_scenario["passagers"]
            noms = [conducteur] + passagers
            adresses = [infos_participants[n]["address"] for n in noms] + [destination]

            trajets.append({
                "voiture": f"Voiture {len(trajets)+1}",
                "conducteur": conducteur,
                "email_conducteur": infos_participants[conducteur]["email"],
                "telephone_conducteur": infos_participants[conducteur]["telephone"],
                "passagers": [
                    {
                        "nom": p,
                        "marche": False,
                        "email": infos_participants[p]["email"],
                        "telephone": infos_participants[p]["telephone"]
                    }
                    for p in passagers
                ],
                "ordre": " → ".join(adresses),
                "google_maps": create_google_maps_link(adresses)
            })

            non_assignes -= set(noms)

    # === CO2: économie pour PASSAGERS uniquement (A/R) ===
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
        "max_passagers_par_voiture": MAX_PASSENGERS  # optionnel mais pratique
    }

