from fastapi import FastAPI, UploadFile, File, Body
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import openrouteservice
import time
from geopy.geocoders import Nominatim
from urllib.parse import quote
import io

app = FastAPI()

# Autoriser toutes les origines (utile pour Glide)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialisation des services
ORS_API_KEY = "ta_clé_API_ORS"
ors_client = openrouteservice.Client(key=ORS_API_KEY)
geolocator = Nominatim(user_agent="covoiturage_app")

# ---------- Utilitaires ----------
def geocode(address):
    try:
        print(f"→ Tentative de géocodage ORS : {address}")
        response = ors_client.pelias_search(text=address)
        coords = response['features'][0]['geometry']['coordinates']
        print(f"✅ ORS OK : {coords}")
        return coords
    except Exception as e:
        print(f"⚠️ ORS échoué : {address} ({e}) → tentative Nominatim")
        try:
            loc = geolocator.geocode(address, timeout=10)
            if loc:
                coords = [loc.longitude, loc.latitude]
                print(f"✅ Nominatim OK : {coords}")
                return coords
            else:
                print(f"❌ Nominatim a échoué : {address}")
        except Exception as en:
            print(f"❌ Erreur Nominatim : {address} ({en})")
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

# ---------- Route JSON (pour Glide) ----------
@app.post("/optimiser_direct")
async def optimiser_direct(data: dict = Body(...)):
    print("=== DONNÉES REÇUES ===")
    print("Players :", data.get("players"))
    print("Destination :", data.get("destination"))
    print("======================")

    joueurs = data.get("players", [])
    destination = data.get("destination", "").strip()
    #max_detour_ratio = data.get("max_detour_ratio", 1.5)

    if not joueurs or not destination:
        return {"trajets": []}

    # Géocodage de la destination dynamique
    DESTINATION_COORD = geocode(destination)
    if not DESTINATION_COORD:
        return {"error": "Échec du géocodage de la destination."}

    # Construction du DataFrame
    df = pd.DataFrame(joueurs)
    df['coord'] = df['address'].apply(geocode)
    df['rotation'] = df.get('rotation', 'moyen')  # par défaut
    print(f"{df['coord'].notnull().sum()} joueurs géocodés (direct)")

    df = df[df['coord'].notnull()].reset_index(drop=True)
    df['duree_directe'] = [get_route_duration([c, DESTINATION_COORD]) for c in df['coord']]
    time.sleep(1)

    # Priorité de conducteur selon rotation
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

        candidats = df[~df['name'].isin(utilises)].copy()
        for _, passenger in candidats.iterrows():
            trajet = [conducteur['coord'], passenger['coord'], DESTINATION_COORD]
            duree_group = get_route_duration(trajet)
            if duree_group <= duree_base * 2:
                groupe.append(passenger['name'])
                coords_groupe.append(passenger['coord'])
                utilises.add(passenger['name'])
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

