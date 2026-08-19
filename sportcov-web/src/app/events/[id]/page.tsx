"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { authHeaders } from "@/lib/auth";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.sport-cov.fr";

type Passager = { nom: string; email: string; telephone: string };
type Trajet = {
  voiture: string;
  conducteur: string;
  telephone_conducteur: string;
  email_conducteur: string;
  passagers: Passager[];
  google_maps: string;
  ordre: string;
};
type OptimiserResult = {
  trajets: Trajet[];
  co2_economise_kg: number;
};
type EventInfo = {
  id: number;
  team_code: string;
  destination: string;
  title?: string;
  event_date?: string;
};

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [event, setEvent] = useState<EventInfo | null>(null);
  const [result, setResult] = useState<OptimiserResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const headers = authHeaders();
    Promise.all([
      fetch(`${API_URL}/events/${id}`, { headers }).then((r) => r.json()),
      fetch(`${API_URL}/events/${id}/trips`, { headers }).then((r) => r.json()),
    ])
      .then(([ev, trips]) => {
        setEvent(ev);
        setResult(trips);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [id]);

  if (loading) return <p className="text-gray-500 p-4">Chargement...</p>;
  if (!result) return <p className="text-red-500 p-4">Impossible de charger les trajets.</p>;

  const date = event?.event_date
    ? new Date(event.event_date).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })
    : null;

  return (
    <div className="space-y-6 pb-8">
      <div className="text-center space-y-1">
        <h1 className="text-2xl font-bold mt-2">{event?.title || "Entraînement"}</h1>
        {event?.destination && (
          <div className="text-gray-600 text-sm">
            <span className="font-medium">Destination :</span> {event.destination}
          </div>
        )}
        {date && <div className="text-gray-500 text-sm">{date}</div>}
      </div>

      <div className="text-sm text-gray-500 text-center">
        {result.trajets.length} voiture{result.trajets.length > 1 ? "s" : ""} —{" "}
        <span className="text-green-600 font-medium">
          🌿 {result.co2_economise_kg.toFixed(1)} kg CO₂ économisés
        </span>
      </div>

      <h2 className="text-lg font-bold">Répartition des trajets</h2>

      <div className="space-y-4">
        {result.trajets.map((trajet, i) => (
          <div key={i} className="bg-gray-50 rounded-xl overflow-hidden border border-gray-200">
            <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-200">
              <span className="font-semibold text-sm">{trajet.voiture}</span>
              {trajet.google_maps && (
                <a
                  href={trajet.google_maps}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="bg-green-400 text-white px-4 py-1.5 rounded-full text-sm font-medium flex items-center gap-1 hover:bg-green-500"
                >
                  🗺 Voir trajet
                </a>
              )}
            </div>
            <div className="divide-y divide-gray-100">
              <div className="px-4 py-3 flex items-center justify-between">
                <div>
                  <div className="font-medium">{trajet.conducteur}</div>
                  <div className="text-xs text-gray-500">conducteur</div>
                </div>
                {trajet.telephone_conducteur && trajet.telephone_conducteur !== "06" && (
                  <a href={`tel:${trajet.telephone_conducteur}`} className="text-green-600 text-sm">
                    📞 Appeler
                  </a>
                )}
              </div>
              {trajet.passagers.map((p, j) => (
                <div key={j} className="px-4 py-3">
                  <div className="font-medium">{p.nom}</div>
                  <div className="text-xs text-gray-500">passager</div>
                </div>
              ))}
              {trajet.passagers.length === 0 && (
                <div className="px-4 py-3 text-sm text-gray-400 italic">Aucun passager</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
