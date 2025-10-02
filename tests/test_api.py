# tests/test_api.py
import importlib.util
import os
from unittest.mock import patch

from fastapi.testclient import TestClient

# Clé factice pour passer le check startup de l'API
os.environ["GOOGLE_API_KEY"] = "dummy"


# --- Mocks Google (geocode + directions) ---
def _fake_response(json_data, status=200):
    class R:
        def __init__(self, j, s):  # minimal pour nos besoins
            self._j = j
            self.status_code = s

        def json(self):
            return self._j

        def raise_for_status(self):
            pass

    return R(json_data, status)


def fake_get(url, params=None, timeout=8):
    params = params or {}
    if "geocode/json" in url:
        addr = params.get("address", "")
        # mini dictionnaire d'adresses -> coordonnées
        book = {"A": (47.0, 0.98), "B": (47.01, 0.99), "DEST": (47.02, 1.00)}
        lat, lng = book.get(addr, (47.0, 1.0))
        return _fake_response(
            {
                "status": "OK",
                "results": [{"geometry": {"location": {"lat": lat, "lng": lng}}}],
            }
        )
    if "directions/json" in url:
        return _fake_response(
            {
                "status": "OK",
                "routes": [
                    {
                        "legs": [
                            {
                                "duration": {"value": 600},   # 10 min
                                "distance": {"value": 5000},  # 5 km
                            }
                        ]
                    }
                ],
            }
        )
    raise AssertionError("URL inattendue dans le test")


def _load_api_module():
    # ⚠️ mets EXACTEMENT le nom du fichier (casse incluse)
    spec = importlib.util.spec_from_file_location("api_module", "api_fastapi.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("Échec du chargement de Api-Fastapi.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_optimiser_direct_minimal():
    with patch("requests.get", side_effect=fake_get):
         patch("api_fastapi.session.get", side_effect=fake_get):
        api_module = _load_api_module()
        client = TestClient(api_module.app)

        payload = {
            "participants": [
                {
                    "name": "Alice",
                    "address": "A",
                    "email": "a@mail.com",
                    "telephone": "0600000001",
                },
                {
                    "name": "Bob",
                    "address": "B",
                    "email": "b@mail.com",
                    "telephone": "0600000002",
                },
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
