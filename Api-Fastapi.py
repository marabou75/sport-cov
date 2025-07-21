from dotenv import load_dotenv
import os

load_dotenv()

from fastapi import FastAPI, Body
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import googlemaps
import time
from geopy.geocoders import Nominatim
from urllib.parse import quote

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GMAPS_API_KEY = os.getenv("GOOGLE_API_KEY")
gmaps = googlemaps.Client(key=GMAPS_API_KEY)
geolocator = Nominatim(user_agent="covoiturage_app")

# Fonction de geocodage

def geocode(address):
    try:
        result = gmaps.geocode(address)
        if result:
            loc = result[0]['geometry']['location']
            return [loc['lng'], loc['lat']]
    except Exception as e:
        print(f"Erreur geocode Google : {e}")
    return None

# Reverse geocoding nettoyé
def reverse_geocode(coords):
    try:
        loc = geolocator.reverse((coords[1], coords[0]), timeout=10)
        if loc and loc.address:
            address = loc.address
            segments_to_remove = ["Loches", "Indre-et-Loire", "Centre-Val de Loire", "France métropolitaine", "France"]
            for seg in segments_to_remove:
                address = address.replace(seg, "")
            return address.replace("  ", " ").strip(" ,→")
    except Exception as e:
        print(f"Reverse geocoding échoué : {e}")
    return f"{coords[1]},{coords[0]}"

# Durée de trajet Google Maps
def get_route_duration(coords):
    try:
        origin = f"{coords[0][1]},{coords[0][0]}"
        destination = f"{coords[-1][1]},{coords[-1][0]}"
        waypoints = [f"{c[1]},{c[0]}" for c in coords[1:-1]]
        result = gmaps.directions(origin=origin, destination=destination, waypoints=waypoints, mode="driving")
        if result:
            return result[0]['legs'][0]['duration']['value']
    except Exception as e:
        print(f"Erreur Google Directions : {e}")
    return float('inf')

@app.post("/optimiser_direct")
async def optimiser_direct(data: dict = Body(...)):
    joueurs = data.get("players", [])
    destination = data.get("destination", "").strip()
    if not joueurs or not destination:
        return {"trajets": []}

    DESTINATION_COORD = geocode(destination)
    if not DESTINATION_COORD:
        return {"error": "Échec du géocodage de la destination."}

    df = pd.DataFrame(joueurs)
    df['coord'] = df['address'].apply(geocode)
    df['rotation'] = df.get('rotation', 'moyen')
    df = df[df['coord'].notnull()].reset_index(drop=True)
    df['duree_directe'] = [get_route_duration([c, DESTINATION_COORD]) for c in df['coord']]
    time.sleep(1)

    def score_rotation(rotation):
        return {"souvent": 0, "moyen": 1, "rare": 2}.get(rotation, 1)

    df = df.sort_values(by="rotation", key=lambda col: col.map(score_rotation)).reset_index(drop=True)

    groupes = []
    utilises = set()

    for _, row in df.iterrows():
        if row['name'] in utilises:
            continue
        conducteur = row
        groupe = [{"nom": conducteur['name'], "marche": False}]
        coords_groupe = [conducteur['coord']]
        utilises.add(conducteur['name'])
        duree_base = conducteur['duree_directe']

        candidats = df[~df['name'].isin(utilises)].copy()
        for _, passenger in candidats.iterrows():
            trajet = [conducteur['coord'], passenger['coord'], DESTINATION_COORD]
            duree_group = get_route_duration(trajet)
            if duree_group <= duree_base * 1.3:
                groupe.append({"nom": passenger['name'], "marche": False})
                coords_groupe.append(passenger['coord'])
                utilises.add(passenger['name'])
            # else: # Option marche à pied temporairement désactivée
            #     distance = haversine(passenger['coord'], conducteur['coord'])
            #     if distance <= 200:
            #         marche_url = get_walking_url(passenger['coord'], conducteur['coord'])
            #         groupe.append({
            #             "nom": passenger['name'],
            #             "marche": True,
            #             "rendez_vous": {
            #                 "coord": conducteur['coord'],
            #                 "adresse": reverse_geocode(conducteur['coord']),
            #                 "marche_maps_url": marche_url
            #             }
            #         })
            #         coords_groupe.append(conducteur['coord'])
            #         utilises.add(passenger['name'])

            if len(groupe) >= 4:
                break
            time.sleep(1)

        groupes.append((groupe, coords_groupe))

    result = []
    for i, (groupe, coords) in enumerate(groupes, 1):
        # → On récupère les adresses exactes à partir de df (plutôt que reverse_geocode)
        noms_du_groupe = [membre['nom'] for membre in groupe]
        adresses = df[df['name'].isin(noms_du_groupe)]['address'].tolist() + [destination]

        # Nettoyage des adresses (enlève virgules multiples, espaces inutiles)
        adresses = [", ".join(filter(None, map(str.strip, adresse.split(',')))) for adresse in adresses]

        origin = quote(adresses[0])
        destination_enc = quote(adresses[-1])
        waypoints = "|".join([quote(a) for a in adresses[1:-1]])
        gmaps_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination_enc}&waypoints={waypoints}"

        result.append({
            "voiture": f"Voiture {i}",
            "conducteur": groupe[0]['nom'],
            "passagers": groupe[1:],
            "ordre": " → ".join(adresses),
            "google_maps": gmaps_url
        })

    return {"trajets": result}

