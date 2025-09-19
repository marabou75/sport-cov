# tests/test_api.py
import os
import importlib.util
from types import SimpleNamespace
from fastapi.testclient import TestClient
import requests

# 1) Clé Google factice pour passer le startup check
os.environ["GOOGLE_API_KEY"] = "dummy"

# 2) Mock très simple de requests.get pour Geocoding & Directions
def _fake_response(json_data, status=200):
    class R:
        def __init__(self, j, s): self._j, self.status_code = j, s
        def json(self): return self._j
        def raise_for_status(self): pass
    return R(json_data, status)

def fake_get(url, params=None, timeout=8):
    params = params or {}
    if "geocode/json" in url:
        addr = params.get("address", "")
        # mini mapping d'adresses -> coordonnées factices
        book = {
            "A": (47.0, 0.98),
            "B": (47.01, 0.99),
            "DEST": (47.02, 1.00),
        }
        lat, lng = book.get(addr, (47.0, 1.0))
        return _fake_response({
            "status": "OK",
            "results": [{"geometry": {"location": {"lat": lat, "lng": lng}}}],
        })
    if "directions/json" in url:
        # Retourne une durée/distance constante pour simplifier
        return _fake_response({
            "status": "OK",
            "routes": [{
                "legs": [{
                    "duration": {"value": 600},   # 10 minutes
                    "distance": {"value": 5000},  # 5 km
                }]
            }]
        })
    raise AssertionError("URL inattendue dans le test")

# 3) Patch de requests.get
requests_get_backup = requests.get
requests.get = fake_get

# 4) Import dynamique du module API-FastAPI.py
spec = importlib.util.spec_from_file_location("api_module", "API-FastAPI.py")
api_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api_module)

client = TestClient(api_module.app)

def test_optimiser_direct_minimal():
    payload = {
        "participants": [
            {"name": "Alice", "address": "A", "email": "a@mail.com", "telephone": "0600000001"},
            {"name": "Bob", "address": "B", "email": "b@mail.com", "telephone": "0600000002"},
        ],
        "destination": "DEST",
    }
    r = client.post("/optimiser_direct", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert "trajets" in data and isinstance(data["trajets"], list)
    # Vérifie quelques champs clés
    t0 = data["trajets"][0]
    assert "conducteur" in t0 and "google_maps" in t0
    assert "co2_economise_kg" in data

# 5) Restore si d'autres tests existent
requests.get = requests_get_backup
