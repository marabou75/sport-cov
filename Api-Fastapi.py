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
        raise HTTPException(status_code=500, detail=f"Erreur géocodage '{address}' : {e}")


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

    coords_participants = {p.name: geocode_address(p.address) for p in participants}
    coord_dest = geocode_address(destination)

    # Durée solo
    durees_solo = {}
    for p in participants:
        durees_solo[p.name] = get_google_duration(coords_participants[p.name], coord_dest)

    seuil_rallonge = 1.3
    voitures = []

    for conducteur in participants:
        voiture = {
            "conducteur": conducteur.name,
            "passagers": [],
            "coords": [coords_participants[conducteur.name]],
            "noms": [conducteur.name]
        }

        for passager in participants:
            if passager.name == conducteur.name:
                continue
            coords_temp = voiture["coords"] + [coords_participants[passager.name], coord_dest]
            duree_avec_passager = get_google_duration(coords_temp[0], coords_temp[1])
            duree_avec_passager += get_google_duration(coords_temp[1], coords_temp[2])

            if duree_avec_passager <= seuil_rallonge * durees_solo[conducteur.name]:
                voiture["coords"].insert(-1, coords_participants[passager.name])
                voiture["noms"].append(passager.name)

        voitures.append(voiture)

    deja_assignes = set()
    trajets_final = []

    for v in voitures:
        passagers_uniques = []
        for nom in v["noms"][1:]:
            if nom not in deja_assignes:
                passagers_uniques.append(nom)
                deja_assignes.add(nom)
        if v["conducteur"] not in deja_assignes:
            deja_assignes.add(v["conducteur"])
            passagers_uniques.insert(0, v["conducteur"])

        adresses_lisibles = [p.address for p in participants if p.name in passagers_uniques]
        adresses_lisibles.append(destination)

        trajets_final.append({
            "voiture": f"Voiture {len(trajets_final)+1}",
            "conducteur": v["conducteur"],
            "passagers": [{"nom": n, "marche": False} for n in passagers_uniques if n != v["conducteur"]],
            "ordre": " → ".join(adresses_lisibles),
            "google_maps": create_google_maps_link(adresses_lisibles)
        })

    return {"trajets": trajets_final}

