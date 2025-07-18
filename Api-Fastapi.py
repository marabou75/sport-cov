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

# CORS pour Glide
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ✅ Ta clé Google Maps API ici
GMAPS_API_KEY = os.getenv("GOOGLE_API_KEY")
gmaps = googlemaps.Client(key=GMAPS_API_KEY)
geolocator = Nominatim(user_agent="covoiturage_app")

# ✅ Fonction de géocodage avec Google
def geocode(address):
    try:
        result = gmaps.geocode(address)
        if result:
            loc = result[0]['geometry']['location']
            return [loc['lng'], loc['lat']]
    except Exception as e:
        print(f"❌ Erreur geocode Google : {e}")
    return None

def reverse_geocode(coords):
    try:
        loc = geolocator.reverse((coords[1], coords[0]), timeout=10)
        return loc.address.replace(",", "")
    except:
        return f"{coords[1]},{coords[0]}"

# ✅ Fonction durée trajet avec Google Directions
def get_route_duration(coords):
    try:
        origin = f"{coords[0][1]},{coords[0][0]}"
        destination = f"{coords[-1][1]},{coords[-1][0]}"
        waypoints = [f"{c[1]},{c[0]}" for c in coords[1:-1]]
        result = gmaps.directions(
            origin=origin,
            destination=destination,
            waypoints=waypoints,
            mode="driving"
        )
        if result:
            return result[0]['legs'][0]['duration']['value']
    except Exception as e:
        print(f"❌ Erreur Google Directions : {e}")
    return float('inf')

@app.post("/optimiser_direct")
async def optimiser_direct(data: dict = Body(...)):
    print("=== DONNÉES REÇUES ===")
    print("Players :", data.get("players"))
    print("Destination :", data.get("destination"))
    print("======================")

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
    print(f"{df['coord'].notnull().sum()} joueurs géocodés")

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
        groupe = [conducteur['name']]
        coords_groupe = [conducteur['coord']]
        utilises.add(conducteur['name'])
        duree_base = conducteur['duree_directe']

        print(f"\n🚗 Nouveau conducteur : {conducteur['name']} (durée directe : {duree_base}s)")

        candidats = df[~df['name'].isin(utilises)].copy()
        for _, passenger in candidats.iterrows():
            trajet = [conducteur['coord'], passenger['coord'], DESTINATION_COORD]
            duree_group = get_route_duration(trajet)
            print(f" ✅ Test {passenger['name']} : {duree_group}s (limite : {duree_base * 1.8}s)")
            if duree_group <= duree_base * 1.8:
                groupe.append(passenger['name'])
                coords_groupe.append(passenger['coord'])
                utilises.add(passenger['name'])
            if len(groupe) >= 4:
                print(" 🛑 Voiture pleine (4 places)")
                break
            time.sleep(1)

        groupes.append((groupe, coords_groupe))

    result = []
    for i, (noms, coords) in enumerate(groupes, 1):
        all_coords = coords + [DESTINATION_COORD]
        adresses = [reverse_geocode(c) for c in all_coords]
        origin = quote(adresses[0])
        destination = quote(adresses[-1])
        waypoints = "|".join([quote(a) for a in adresses[1:-1]])
        gmaps_url = f"https://www.google.com/maps/dir/?api=1&origin={origin}&destination={destination}&waypoints={waypoints}"
        result.append({
            "voiture": f"Voiture {i}",
            "conducteur": noms[0],
            "passagers": noms[1:] if len(noms) > 1 else [],
            "ordre": " → ".join(adresses),
            "google_maps": gmaps_url
        })

    return {"trajets": result}

