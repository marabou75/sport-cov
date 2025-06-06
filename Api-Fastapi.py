from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import openrouteservice
import time
from geopy.geocoders import Nominatim
from typing import List
import io
from urllib.parse import quote

app = FastAPI()

# Autorise tout (pour test Glide)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Init services
ORS_API_KEY = "5b3ce3597851110001cf624848a79956802748508b86e59d71fc9304"  # À remplacer avant déploiement
ors_client = openrouteservice.Client(key=ORS_API_KEY)
geolocator = Nominatim(user_agent="covoiturage_app")

# Destination fixe pour démo (Stade de l'île d'Or)
DESTINATION_COORD = [0.99193, 47.41223]

# --------------------------
# Utilitaires
# --------------------------
def geocode(address):
    try:
        response = ors_client.pelias_search(text=address)
        return response['features'][0]['geometry']['coordinates']
    except:
        return None

def reverse_geocode(coords):
    try:
        loc = geolocator.reverse((coords[1], coords[0]), timeout=10)
        return loc.address.replace(",", "")
    except:
        return f"{coords[1]},{coords[0]}"

def get_route_duration(coords):
    try:
        route = ors_client.directions(coords, profile='driving-car')
        return route['routes'][0]['summary']['duration']
    except:
        return float('inf')

# --------------------------
# Route principale
# --------------------------
@app.post("/optimiser")
async def optimiser(file: UploadFile = File(...)):
    content = await file.read()
    df = pd.read_csv(io.StringIO(content.decode("utf-8")))

    df['coord'] = df['Adresse de départ'].apply(geocode)
    print(f"{df['coord'].notnull().sum()} joueurs géocodés avec     succès")
    df = df[df['coord'].notnull()].reset_index(drop=True)
    

    df['duree_directe'] = [get_route_duration([c, DESTINATION_COORD]) for c in df['coord']]
    time.sleep(1)

    groupes = []
    utilises = set()
    for _, row in df.iterrows():
        if row['Nom'] in utilises:
            continue
        conducteur = row
        groupe = [conducteur['Nom']]
        coords_groupe = [conducteur['coord']]
        utilises.add(conducteur['Nom'])
        duree_base = conducteur['duree_directe']

        candidats = df[~df['Nom'].isin(utilises)].copy()
        for _, passenger in candidats.iterrows():
            trajet = [conducteur['coord'], passenger['coord'], DESTINATION_COORD]
            duree_group = get_route_duration(trajet)
            if duree_group <= duree_base * 1.5:
                groupe.append(passenger['Nom'])
                coords_groupe.append(passenger['coord'])
                utilises.add(passenger['Nom'])
            if len(groupe) >= 4:
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
