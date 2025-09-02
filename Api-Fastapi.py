# 1) en haut du fichier (imports/constantes)
from itertools import combinations
MAX_PASSENGERS = int(os.getenv("MAX_PASSENGERS", "3"))

# ... imports + constantes identiques (CO2_PER_KM, MAX_PASSENGERS, etc.)

@app.post("/optimiser_direct")
async def optimiser_trajets(data: InputData):
    participants = data.participants
    infos_participants = {p.name: {"email": p.email, "telephone": p.telephone, "address": p.address} for p in participants}
    destination = data.destination

    # géocodage & durées directes identiques...
    coords = {p.name: geocode_address(p.address) for p in participants}
    coord_dest = geocode_address(destination)
    durees_directes = {p.name: get_google_duration(coords[p.name], coord_dest) for p in participants}

    seuil_rallonge = 2.3
    non_assignes = set(p.name for p in participants)
    trajets = []

    while non_assignes:
        meilleur_scenario = None
        # → priorité : plus de passagers, puis durée la plus courte
        best_passengers_count = -1
        best_duration = float("inf")

        for conducteur_candidat in list(non_assignes):
            try:
                # 1) passagers compatibles (selon rallonge du conducteur_candidat)
                passagers_compatibles = []
                for autre in non_assignes:
                    if autre == conducteur_candidat:
                        continue
                    duree_aller = get_google_duration(coords[conducteur_candidat], coords[autre])
                    duree_retour = get_google_duration(coords[autre], coord_dest)
                    if (duree_aller + duree_retour) <= seuil_rallonge * durees_directes[conducteur_candidat]:
                        passagers_compatibles.append(autre)

                # 2) on essaye chaque membre comme conducteur
                groupe = [conducteur_candidat] + passagers_compatibles
                for conducteur in groupe:
                    others = [p for p in groupe if p != conducteur]
                    limit = min(MAX_PASSENGERS, len(others))

                    # 3) tester toutes les combinaisons de passagers (0..limit)
                    for k in range(limit, -1, -1):
                        from itertools import combinations
                        for subset in combinations(others, k):
                            points = [coords[conducteur]] + [coords[p] for p in subset] + [coord_dest]
                            duree_trajet = sum(get_google_duration(points[i], points[i+1])
                                               for i in range(len(points)-1))

                            # priorité au plus grand k, puis à la plus petite durée
                            if (k > best_passengers_count) or (k == best_passengers_count and duree_trajet < best_duration):
                                best_passengers_count = k
                                best_duration = duree_trajet
                                meilleur_scenario = {
                                    "conducteur": conducteur,
                                    "passagers": list(subset)
                                }
            except Exception:
                continue

        # création du trajet pour ce tour
        if not meilleur_scenario:
            seul = non_assignes.pop()
            adresse = infos_participants[seul]["address"]
            trajets.append({
                "voiture": f"Voiture {len(trajets)+1}",
                "conducteur": seul,
                "email_conducteur": infos_participants[seul]["email"],
                "telephone_conducteur": infos_participants[seul]["telephone"],
                "passagers": [],
                "ordre": f"{adresse} → {destination}",
                "google_maps": create_google_maps_link([adresse, destination])
            })
        else:
            conducteur = meilleur_scenario["conducteur"]
            passagers = meilleur_scenario["passagers"]
            noms = [conducteur] + passagers
            adresses = [infos_participants[n]["address"] for n in noms] + [destination]

