from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import List, Dict, Optional
import openrouteservice
from openrouteservice import convert
import urllib.parse
import requests

app = FastAPI()

ORS_API_KEY = "your_openrouteservice_api_key"  # Remplacer par votre clé OpenRouteService
GOOGLE_API_KEY = "your_google_api_key"  # Remplacer par votre clé Google Maps
ors_client = openrouteservice.Client(key=ORS_API_KEY)


class Participant(BaseModel):
    name: str
    address: str


class InputData(BaseModel):
    participants: List[Participant]
    destination: str


def geocode_address(address: str):
    try:
        url = f"https://maps.googleapis.com/maps/api/geocode/json"
        params = {"address": address, "key": GOOGLE_API_KEY}
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data["status"] == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return [loc["lng"], loc["lat"]]
        else:
            raise HTTPException(status_code=400, detail=f"Adresse introuvable : {address}")
    except Exception as e:
        print(f"[ERREUR] géocodage '{address}': {e}")
        raise HTTPException(status_code=500, detail=f"Erreur lors du géocodage de l'adresse '{address}' : {e}")


def reverse_geocode(lat: float, lon: float) -> str:
    try:
        url = f"https://maps.googleapis.com/maps/api/geocode/json"
        params = {"latlng": f"{lat},{lon}", "key": GOOGLE_API_KEY, "language": "fr"}
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        data = response.json()
        if data["status"] == "OK":
            return data["results"][0]["formatted_address"]
        else:
            return f"{lat},{lon}"
    except:
        return f"{lat},{lon}"


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

    # Géocoder les adresses
    coords = []
    for p in participants:
        coords.append(geocode_address(p.address))

    coord_dest = geocode_address(destination)

    # Calculer la durée de chaque participant seul
    durees_solo = {}
    for i, p in enumerate(participants):
        try:
            route = ors_client.directions(
                coordinates=[coords[i], coord_dest],
                profile="driving-car",
                format="geojson"
            )
            durees_solo[p.name] = route["features"][0]["properties"]["summary"]["duration"]
        except Exception:
            durees_solo[p.name] = float("inf")

    # Affecter chaque participant à une voiture (greedy)
    trajets = []
    voitures = []
    seuil_rallonge = 1.3  # max 30% de détour

    for conducteur in participants:
        voiture = {
            "conducteur": conducteur.name,
            "passagers": [],
            "coords": [geocode_address(conducteur.address)],
            "noms": [conducteur.name]
        }

        for passager in participants:
            if passager.name == conducteur.name:
                continue

            coords_temp = voiture["coords"] + [geocode_address(passager.address), coord_dest]
            try:
                route = ors_client.directions(
                    coordinates=coords_temp,
                    profile="driving-car",
                    format="geojson"
                )
                duree_avec_passager = route["features"][0]["properties"]["summary"]["duration"]
                duree_solo = durees_solo[conducteur.name]
                if duree_avec_passager <= seuil_rallonge * duree_solo:
                    voiture["coords"].insert(-1, geocode_address(passager.address))
                    voiture["noms"].append(passager.name)
            except Exception:
                continue

        voitures.append(voiture)

    # Nettoyer les doublons (un passager ne peut pas être dans 2 voitures)
    deja_assignes = set()
    trajets_final = []

    for i, v in enumerate(voitures):
        passagers_uniques = []
        for nom in v["noms"][1:]:
            if nom not in deja_assignes:
                passagers_uniques.append(nom)
                deja_assignes.add(nom)
        if v["conducteur"] not in deja_assignes:
            deja_assignes.add(v["conducteur"])
            passagers_uniques.insert(0, v["conducteur"])
        coords_trajet = [geocode_address(p.address) for p in participants if p.name in passagers_uniques]
        coords_trajet.append(coord_dest)

        # Récupérer les adresses lisibles
        adresses_lisibles = []
        for lon, lat in coords_trajet:
            adresse = reverse_geocode(lat, lon)
            propre = ", ".join([x.strip() for x in adresse.split(',') if x.strip()])
            adresses_lisibles.append(propre)

        trajet = {
            "voiture": f"Voiture {len(trajets_final)+1}",
            "conducteur": v["conducteur"],
            "passagers": [{"nom": nom, "marche": False} for nom in passagers_uniques if nom != v["conducteur"]],
            "ordre": " → ".join(adresses_lisibles),
            "google_maps": create_google_maps_link(adresses_lisibles)
        }
        trajets_final.append(trajet)

    return {"trajets": trajets_final}

