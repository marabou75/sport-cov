from typing import Tuple
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import urllib.parse
import requests
import os
from dotenv import load_dotenv
from functools import lru_cache

load_dotenv()
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

app = FastAPI()

@app.on_event("startup")
def check_api_key():
    if not GOOGLE_API_KEY:
        # Arrête l'app proprement avec un message clair
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
    # Vérifie la clé API avant tout appel
    if not GOOGLE_API_KEY:
        raise HTTPException(status_code=500, detail="GOOGLE_API_KEY manquante.")

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_API_KEY}

    try:
        # timeout ajouté (augmente si besoin)
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
    """Wrapper qui gère les erreurs et normalise l'adresse."""
    try:
        lng, lat = geocode_address_cached(address.strip())
        return (lng, lat)
    except HTTPException:
        # on propage tel quel pour que FastAPI retourne le bon status
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur geocodage '{address}' : {e}")

@lru_cache(maxsize=256)
def get_google_duration(origin, destination):
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
    infos_participants = {p.name: {"email": p.email, "telephone": p.telephone} for p in participants}
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

    seuil_rallonge = 1.7
    non_assignes = set(p.name for p in participants)
    trajets = []

    while non_assignes:
        meilleur_scenario = None
        duree_min = float('inf')

        for conducteur_candidat in non_assignes:
            try:
                passagers_compatibles = []
                for autre in non_assignes:
                    if autre == conducteur_candidat:
                        continue
                    duree_aller = get_google_duration(coords[conducteur_candidat], coords[autre])
                    duree_retour = get_google_duration(coords[autre], coord_dest)
                    duree_total = duree_aller + duree_retour
                    if duree_total <= seuil_rallonge * durees_directes[conducteur_candidat]:
                        passagers_compatibles.append(autre)

                groupe = [conducteur_candidat] + passagers_compatibles
                for conducteur in groupe:
                    passagers = [p for p in groupe if p != conducteur]
                    points = [coords[conducteur]] + [coords[p] for p in passagers] + [coord_dest]
                    duree_trajet = sum(get_google_duration(points[i], points[i+1]) for i in range(len(points)-1))

                    print(f"[DEBUG] Conducteur testé : {conducteur}")
                    print(f"[DEBUG] Passagers évalués : {passagers}")
                    print(f"[DEBUG] Durée totale du trajet : {duree_trajet/60:.1f} min")

                    if duree_trajet < duree_min:
                        duree_min = duree_trajet
                        meilleur_scenario = {
                            "conducteur": conducteur,
                            "passagers": passagers
                        }

            except Exception as e:
                print(f"Erreur lors du test de {conducteur_candidat} : {e}")

        if not meilleur_scenario:
            seul = non_assignes.pop()
            adresse = next(p.address for p in participants if p.name == seul)
            trajets.append({
                "voiture": f"Voiture {len(trajets)+1}",
                "conducteur": seul,
                "passagers": [],
                "ordre": f"{adresse} → {destination}",
                "google_maps": create_google_maps_link([adresse, destination])
            })
        else:
            conducteur = meilleur_scenario["conducteur"]
            passagers = meilleur_scenario["passagers"]
            noms = [conducteur] + passagers
            adresses = [p.address for p in participants if p.name in noms] + [destination]

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

    return {"trajets": trajets}

