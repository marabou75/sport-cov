"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL || "https://api.sport-cov.fr";

type Team = { id: number; name: string; code: string; logo_url?: string | null };
type Event = { id: number; destination: string; title?: string; event_date?: string; team_code: string };

export default function AccueilPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [events, setEvents] = useState<Event[]>([]);
  const [selectedTeam, setSelectedTeam] = useState<number | null>(null);

  useEffect(() => {
    apiFetch(`${API}/teams`)
      .then(r => r.ok ? r.json() : [])
      .then(data => {
        if (!Array.isArray(data)) return;
        setTeams(data);
        if (data.length > 0) setSelectedTeam(data[0].id);
      })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!selectedTeam) return;
    apiFetch(`${API}/teams/${selectedTeam}/events`)
      .then(r => r.ok ? r.json() : [])
      .then(data => Array.isArray(data) ? setEvents(data) : null)
      .catch(console.error);
  }, [selectedTeam]);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3 flex-wrap">
        {teams.length > 0 && (
          <select
            className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
            value={selectedTeam ?? ""}
            onChange={(e) => setSelectedTeam(Number(e.target.value))}
          >
            {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        )}
        <Link href="/equipes/new"
          className="bg-green-400 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-green-500">
          + Créer une équipe
        </Link>
      </div>

      <h2 className="text-xl font-bold">Historique des événements</h2>

      {events.length === 0 ? (
        <p className="text-gray-500 text-sm">Aucun événement pour cette équipe.</p>
      ) : (
        <div className="space-y-3">
          {events.map(evt => (
            <Link key={evt.id} href={`/events/${evt.id}`}
              className="flex items-center justify-between bg-white border border-gray-200 rounded-xl p-4 hover:border-green-400 transition-colors">
              <div>
                <div className="font-semibold">{evt.title || evt.destination}</div>
                <div className="text-xs text-gray-400 mt-0.5">→ {evt.destination}</div>
                {evt.event_date && (
                  <div className="text-xs text-gray-400 mt-0.5">
                    {new Date(evt.event_date).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}
                  </div>
                )}
              </div>
              <span className="text-gray-400 text-xl">›</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
