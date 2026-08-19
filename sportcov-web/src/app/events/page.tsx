"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "https://api.sport-cov.fr";

type Event = {
  id: number;
  team_code: string;
  destination: string;
  title?: string | null;
  event_date?: string | null;
  created_at: string;
};

export default function EventsPage() {
  const [teamId, setTeamId] = useState<number | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Récupérer l'équipe actuelle depuis localStorage + écouter les changements
  useEffect(() => {
    const loadTeam = () => {
      const stored = window.localStorage.getItem("sportcov.currentTeamId");
      setTeamId(stored ? Number(stored) : null);
    };
    loadTeam();

    const handler = (e: any) => {
      const id = e.detail?.teamId;
      if (typeof id === "number" || typeof id === "string") {
        setTeamId(Number(id));
      }
    };

    window.addEventListener("sportcov-team-changed", handler);
    return () => window.removeEventListener("sportcov-team-changed", handler);
  }, []);

  // Charger les événements de l'équipe courante
  useEffect(() => {
    if (!teamId) {
      setEvents([]);
      return;
    }

    const fetchEvents = async () => {
      try {
        setLoading(true);
        setError(null);
        const res = await fetch(`${API_URL}/teams/${teamId}/events`);
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        }
        const data: Event[] = await res.json();
        setEvents(data);
      } catch (err: any) {
        console.error(err);
        setError("Impossible de charger les événements.");
        setEvents([]);
      } finally {
        setLoading(false);
      }
    };

    fetchEvents();
  }, [teamId]);

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between gap-2">
        <div>
          <h2 className="text-2xl font-semibold mb-1">Événements</h2>
          <p className="text-sm text-slate-600">
            Matchs, entraînements, tournois… pour l’équipe sélectionnée.
          </p>
        </div>
      </header>

      {!teamId && (
        <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded px-3 py-2">
          Aucune équipe sélectionnée. Choisis une équipe dans le menu de gauche.
        </p>
      )}

      {error && (
        <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded px-3 py-2">
          {error}
        </p>
      )}

      {loading && <p>Chargement des événements…</p>}

      {!loading && teamId && events.length === 0 && (
        <p className="text-sm text-slate-600">
          Aucun événement encore créé pour cette équipe.
        </p>
      )}

      {!loading && events.length > 0 && (
        <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
          <table className="min-w-full text-sm">
            <thead className="bg-slate-100 text-slate-700">
              <tr>
                <th className="px-3 py-2 text-left">Nom</th>
                <th className="px-3 py-2 text-left">Date</th>
                <th className="px-3 py-2 text-left">Destination</th>
                <th className="px-3 py-2 text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.id} className="border-t">
                  <td className="px-3 py-2">
                    {e.title || "(Sans titre)"}
                  </td>
                  <td className="px-3 py-2">
                    {e.event_date
                      ? new Date(e.event_date).toLocaleString("fr-FR")
                      : "—"}
                  </td>
                  <td className="px-3 py-2">{e.destination}</td>
                  <td className="px-3 py-2">
                    <Link
                      href={`/events/${e.id}`}
                      className="text-blue-600 hover:underline"
                    >
                      Voir les trajets →
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
