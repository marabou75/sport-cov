"use client";

import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL || "https://api.sport-cov.fr";

type Team = { id: number; name: string };
type EventInfo = { id: number; destination: string; title?: string; event_date?: string };
type Co2Voiture = { voiture: string; conducteur: string; nb_passagers: number; co2_voiture_kg: number };
type TripResult = { co2_economise_kg: number; co2_par_voiture: Co2Voiture[]; trajets: { voiture: string }[] };

export default function Co2Page() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [events, setEvents] = useState<EventInfo[]>([]);
  const [selectedTeam, setSelectedTeam] = useState<number | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<number | null>(null);
  const [result, setResult] = useState<TripResult | null>(null);

  useEffect(() => {
    apiFetch(`${API}/teams`)
      .then(r => r.ok ? r.json() : [])
      .then(d => { if (!Array.isArray(d)) return; setTeams(d); if (d.length > 0) setSelectedTeam(d[0].id); })
      .catch(console.error);
  }, []);

  useEffect(() => {
    if (!selectedTeam) return;
    setEvents([]); setSelectedEvent(null); setResult(null);
    apiFetch(`${API}/teams/${selectedTeam}/events`)
      .then(r => r.ok ? r.json() : [])
      .then(d => { if (!Array.isArray(d)) return; setEvents(d); if (d.length > 0) setSelectedEvent(d[0].id); })
      .catch(console.error);
  }, [selectedTeam]);

  useEffect(() => {
    if (!selectedEvent) return;
    setResult(null);
    apiFetch(`${API}/events/${selectedEvent}/trips`)
      .then(r => r.ok ? r.json() : null)
      .then(d => d && setResult(d))
      .catch(console.error);
  }, [selectedEvent]);

  const selectedEventInfo = events.find(e => e.id === selectedEvent);

  return (
    <div className="space-y-6 pb-8">
      <h1 className="text-2xl font-bold">CO² économisé</h1>

      <div className="flex gap-3 flex-wrap">
        <select
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
          value={selectedTeam ?? ""}
          onChange={e => { setSelectedTeam(Number(e.target.value)); }}
        >
          {teams.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
        </select>
        <select
          className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
          value={selectedEvent ?? ""}
          onChange={e => setSelectedEvent(Number(e.target.value))}
          disabled={events.length === 0}
        >
          {events.length === 0
            ? <option>Aucun événement</option>
            : events.map(e => <option key={e.id} value={e.id}>{e.title || e.destination}</option>)
          }
        </select>
      </div>

      {result ? (
        <>
          <div className="bg-green-50 border border-green-200 rounded-2xl p-6 text-center space-y-2">
            <div className="text-5xl font-bold text-green-500">
              {result.co2_economise_kg.toFixed(1)} kg
            </div>
            <div className="text-gray-600 font-medium">de CO² économisés</div>
            {selectedEventInfo && (
              <div className="text-sm text-gray-500">
                {selectedEventInfo.title || selectedEventInfo.destination}
                {selectedEventInfo.event_date && (
                  <> — {new Date(selectedEventInfo.event_date).toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}</>
                )}
              </div>
            )}
            <div className="text-sm text-gray-500">
              {result.trajets.length} voiture{result.trajets.length > 1 ? "s" : ""} pour{" "}
              {result.co2_par_voiture.reduce((s, v) => s + v.nb_passagers + 1, 0)} participants
            </div>
          </div>

          <div className="space-y-2">
            {result.co2_par_voiture.map((v, i) => (
              <div key={i} className="flex items-center justify-between border border-gray-200 rounded-xl px-4 py-3 bg-white">
                <div>
                  <div className="font-medium">{v.voiture}</div>
                  <div className="text-sm text-gray-500">
                    {v.conducteur} · {v.nb_passagers} passager{v.nb_passagers > 1 ? "s" : ""}
                  </div>
                </div>
                <div className="text-right">
                  <div className="text-green-600 font-semibold text-sm">
                    {v.co2_voiture_kg.toFixed(2)} kg
                  </div>
                  <div className="text-xs text-gray-400">CO² écon.</div>
                </div>
              </div>
            ))}
          </div>
        </>
      ) : (
        <p className="text-gray-400 text-sm text-center py-12">
          {teams.length === 0 ? "Aucune équipe — créez-en une d'abord." : "Sélectionnez un événement pour voir les statistiques."}
        </p>
      )}
    </div>
  );
}
