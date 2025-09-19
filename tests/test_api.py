import importlib.util
import os

import requests
from fastapi.testclient import TestClient

# Clé factice pour passer l'event startup
os.environ["GOOGLE_API_KEY"] = "dummy"

# --- Mock Google (geocode + directions) ---
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
        book = {"A": (47.0, 0.98), "B": (47.01, 0.99), "DEST": (47.02, 1.00)}
        lat, lng = book.get(addr, (47.0, 1.0))
        return _fake_response({"status": "OK",
                               "results": [{"geometry": {"location": {"lat": lat, "lng": lng}}}]})
    if "directions/json" in url:
        return _fake_response({"status": "OK",
                               "routes": [{"legs": [{"duration": {"value": 600},
                                                     "distance": {"value": 5000}}]}]})
    raise AssertionError("URL inattendue")

_requests_get_backup = requests.get
requests.get = fake_get

# ⚠️ respecte exactement le nom du fichier dans ton repo
spec = importlib.util.spec_from_file_location("api_module", "Api-Fastapi.py")
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
    assert isinstance(data.get("trajets"), list)
    assert "co2_economise_kg" in data
    t0 = data["trajets"][0]
    assert "conducteur" in t0 and "google_maps" in t0

# restore pour ne pas polluer d'autres tests
requests.get = _requests_get_backup
