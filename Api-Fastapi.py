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

class Participant(BaseModel):
    name: str
    address: str

class InputData(BaseModel):
    participants: List[Participant]
    destination: str

@lru_cache(maxsize=128)
def geocode_address_cached(address: str):
    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {"address": address, "key": GOOGLE_API_KEY}
    response = requests.get(url, params=params, timeout=5)
    response.raise_for_status()
    data = response.json()
    if data["status"] == "OK":
        loc = data["results"][0]["geometry"]["location"]
        return (loc["lng"], loc["lat"])
    else:
        raise HTTPException(status_code=400, detail=f"Adresse introuvable : {address}")

def geocode_address(address: str):
    try:
        return list(geocode_address_cached(address))
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
    response = requests.get(url, params=params)
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
    destination = data.destination

    coords = {p.name: geocode_address(p.address) for p in participants}
    coord_dest = geocode_address(destination)

    # Durée directe de chaque participant
    durees_directes = {
        p.name: get_google_duration(coords[p.name], coord_dest) for p in participants
    }

    seuil_rallonge = 1.7
    non_assignes = set(p.name for p in participants)
    trajets = []

    while non_assignes:
        meilleurs_trajet = None
        duree_min = float('inf')

        # Pour chaque conducteur potentiel non encore assigné
        for conducteur in non_assignes:
            groupe = [conducteur]
            duree_total = 0
            passagers = []

            for passager in non_assignes:
                if passager == conducteur:
                    continue

                # Test avec ce passager en plus
                duree_aller = get_google_duration(coords[conducteur], coords[passager])
                duree_retour = get_google_duration(coords[passager], coord_dest)
                duree_total = duree_aller + duree_retour

                if duree_total <= seuil_rallonge * durees_directes[conducteur]:
                    passagers.append(passager)

            # Calcul du trajet complet avec tous les passagers compatibles
            points = [coords[conducteur]] + [coords[p] for p in passagers] + [coord_dest]
            duree_trajet = 0
            for i in range(len(points) - 1):
                duree_trajet += get_google_duration(points[i], points[i + 1])

            if duree_trajet < duree_min:
                duree_min = duree_trajet
                meilleurs_trajet = {
                    "conducteur": conducteur,
                    "passagers": passagers,
                }

        if not meilleurs_trajet:
            # Aucun covoiturage possible pour les restants
            seul = non_assignes.pop()
            trajets.append({
                "voiture": f"Voiture {len(trajets)+1}",
                "conducteur": seul,
                "passagers": [],
                "ordre": f"{[p.address for p in participants if p.name == seul][0]} → {destination}",
                "google_maps": create_google_maps_link([
                    [p.address for p in participants if p.name == seul][0],
                    destination
                ])
            })
        else:
            conducteur = meilleurs_trajet["conducteur"]
            passagers = meilleurs_trajet["passagers"]
            noms = [conducteur] + passagers
            adresses = [p.address for p in participants if p.name in noms]
            adresses.append(destination)

            trajets.append({
                "voiture": f"Voiture {len(trajets)+1}",
                "conducteur": conducteur,
                "passagers": [{"nom": p, "marche": False} for p in passagers],
                "ordre": " → ".join(adresses),
                "google_maps": create_google_maps_link(adresses)
            })

            non_assignes -= set(noms)

    return {"trajets": trajets}


