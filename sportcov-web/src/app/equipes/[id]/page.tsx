
"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import SmsLinks from "@/components/SmsLinks";
import { authHeaders, apiFetch } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL || "https://api.sport-cov.fr";

type Team = { id: number; name: string; code: string };
type Participant = { id: number; name: string; address: string; telephone?: string; email?: string; token: string };
type Passager = { nom: string; marche: boolean; telephone?: string };
type Trajet = { voiture: string; conducteur: string; telephone_conducteur: string; passagers: Passager[]; google_maps: string; ordre: string };
type Result = { trajets: Trajet[]; co2_economise_kg: number };
type EventOut = { id: number; title: string | null; destination: string; created_at: string };

export default function TeamPage() {
  const { id } = useParams<{ id: string }>();
  const [team, setTeam] = useState<Team | null>(null);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [events, setEvents] = useState<EventOut[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [lastEventId, setLastEventId] = useState<number | null>(null);

  // Formulaire joueur
  const [pName, setPName] = useState("");
  const [pAddress, setPAddress] = useState("");
  const [pPhone, setPPhone] = useState("");
  const [pEmail, setPEmail] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [pLoading, setPLoading] = useState(false);

  // Formulaire optimisation
  const [destination, setDestination] = useState("");
  const [eventTitle, setEventTitle] = useState("");
  const [selected, setSelected] = useState<number[]>([]);
  const [optimizing, setOptimizing] = useState(false);
  const [optError, setOptError] = useState("");

  useEffect(() => { loadAll(); }, [id]);

  async function loadAll() {
    const [tRes, pRes, eRes] = await Promise.all([
      fetch(`${API}/teams`, { headers: authHeaders() }),
      apiFetch(`${API}/teams/${id}/participants`),
      apiFetch(`${API}/teams/${id}/events`),
    ]);
    const teams: Team[] = await tRes.json();
    setTeam(teams.find(t => t.id === Number(id)) || null);
    const parts: Participant[] = await pRes.json();
    setParticipants(parts);
    setSelected(parts.map(p => p.id));
    setEvents(await eRes.json());
  }

  async function addParticipant(e: React.FormEvent) {
    e.preventDefault(); setPLoading(true);
    await fetch(`${API}/teams/${id}/participants`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({ name: pName, address: pAddress, telephone: pPhone || null, email: pEmail || null }),
    });
    setPName(""); setPAddress(""); setPPhone(""); setPEmail(""); setShowForm(false); setPLoading(false);
    loadAll();
  }

  async function deleteParticipant(pid: number) {
    if (!confirm("Supprimer ce joueur ?")) return;
    await fetch(`${API}/participants/${pid}`, { method: "DELETE", headers: authHeaders() });
    loadAll();
  }

  async function optimize(e: React.FormEvent) {
    e.preventDefault();
    if (selected.length < 2) { setOptError("Sélectionnez au moins 2 joueurs."); return; }
    if (!destination.trim()) { setOptError("Indiquez la destination."); return; }
    setOptimizing(true); setOptError(""); setResult(null);
    try {
      const res = await fetch(`${API}/teams/${id}/carpool/optimize`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ event_address: destination, participant_ids: selected, event_title: eventTitle || null }),
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail || "Erreur"); }
      const r = await res.json();
      setResult(r);
      // Récupérer l'id du dernier événement créé
      const evRes = await apiFetch(`${API}/teams/${id}/events`);
      const evs = await evRes.json();
      if (evs.length > 0) setLastEventId(evs[0].id);
      loadAll();
    } catch (err: any) { setOptError(err.message); }
    finally { setOptimizing(false); }
  }

  function toggleAll() {
    setSelected(selected.length === participants.length ? [] : participants.map(p => p.id));
  }

  return (
    <div className="space-y-8">
      {/* En-tête équipe */}
      <div className="flex items-center gap-3">
        <Link href="/equipes" className="text-gray-400 hover:text-gray-600">← Équipes</Link>
        <h1 className="text-2xl font-bold">{team?.name ?? "Chargement…"}</h1>
      </div>

      {/* Joueurs */}
      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Joueurs ({participants.length})</h2>
          <button
            onClick={() => setShowForm(!showForm)}
            className="bg-green-400 text-white px-4 py-1.5 rounded-full text-sm font-medium hover:bg-green-500"
          >
            {showForm ? "Annuler" : "+ Ajouter"}
          </button>
        </div>

        {showForm && (
          <form onSubmit={addParticipant} className="bg-gray-50 rounded-xl p-4 space-y-3 border border-gray-200">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="text-xs font-medium text-gray-600">Nom *</label>
                <input required value={pName} onChange={e => setPName(e.target.value)}
                  placeholder="Jean Dupont"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mt-1 focus:outline-none focus:border-green-400" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600">Adresse *</label>
                <input required value={pAddress} onChange={e => setPAddress(e.target.value)}
                  placeholder="12 rue des lilas, 37400 Amboise"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mt-1 focus:outline-none focus:border-green-400" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600">Téléphone</label>
                <input value={pPhone} onChange={e => setPPhone(e.target.value)}
                  placeholder="06 12 34 56 78"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mt-1 focus:outline-none focus:border-green-400" />
              </div>
              <div>
                <label className="text-xs font-medium text-gray-600">Email</label>
                <input type="email" value={pEmail} onChange={e => setPEmail(e.target.value)}
                  placeholder="jean@email.fr"
                  className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm mt-1 focus:outline-none focus:border-green-400" />
              </div>
            </div>
            <button type="submit" disabled={pLoading}
              className="w-full bg-green-400 text-white py-2 rounded-full text-sm font-medium hover:bg-green-500 disabled:opacity-60">
              {pLoading ? "Ajout…" : "Ajouter le joueur"}
            </button>
          </form>
        )}

        {participants.length === 0 ? (
          <p className="text-gray-400 text-sm">Aucun joueur. Ajoutez-en pour commencer.</p>
        ) : (
          <div className="divide-y divide-gray-100 border border-gray-200 rounded-xl overflow-hidden">
            {participants.map(p => (
              <div key={p.id} className="flex items-center gap-3 px-4 py-3 bg-white">
                <input type="checkbox" checked={selected.includes(p.id)}
                  onChange={e => setSelected(e.target.checked ? [...selected, p.id] : selected.filter(x => x !== p.id))}
                  className="accent-green-400 w-4 h-4 flex-shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm">{p.name}</div>
                  <div className="text-xs text-gray-500 truncate">{p.address}</div>
                </div>
                {p.telephone && <a href={`tel:${p.telephone}`} className="text-xs text-green-500 whitespace-nowrap">{p.telephone}</a>}
                <button onClick={() => deleteParticipant(p.id)} className="text-gray-300 hover:text-red-400 text-lg leading-none flex-shrink-0">×</button>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Lancer le covoiturage */}
      {participants.length >= 2 && (
        <section className="space-y-4 border-t border-gray-100 pt-6">
          <h2 className="text-lg font-semibold">🚗 Lancer le covoiturage</h2>
          <form onSubmit={optimize} className="space-y-3">
            <div>
              <label className="text-sm font-medium text-gray-700">Destination *</label>
              <input required value={destination} onChange={e => setDestination(e.target.value)}
                placeholder="Stade de l'île d'or, 37400 Amboise"
                className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm mt-1 focus:outline-none focus:border-green-400 focus:ring-1 focus:ring-green-400" />
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700">Nom de l&apos;événement</label>
              <input value={eventTitle} onChange={e => setEventTitle(e.target.value)}
                placeholder="Match vs Tours – 14 septembre"
                className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm mt-1 focus:outline-none focus:border-green-400 focus:ring-1 focus:ring-green-400" />
            </div>
            <div className="flex items-center gap-2 text-sm text-gray-600">
              <button type="button" onClick={toggleAll} className="text-green-500 hover:underline text-xs">
                {selected.length === participants.length ? "Tout désélectionner" : "Tout sélectionner"}
              </button>
              <span className="text-gray-400">— {selected.length}/{participants.length} joueurs sélectionnés</span>
            </div>
            {optError && <p className="text-red-500 text-sm">{optError}</p>}
            <button type="submit" disabled={optimizing}
              className="w-full bg-green-400 hover:bg-green-500 text-white font-semibold py-3 rounded-full transition-colors disabled:opacity-60">
              {optimizing ? "Calcul en cours…" : "✨ Optimiser les trajets"}
            </button>
          </form>
        </section>
      )}

      {/* Résultats d'optimisation */}
      {result && (
        <section className="space-y-4 border-t border-gray-100 pt-6">
          <div className="text-center space-y-1">
            <h2 className="text-xl font-bold">Répartition des trajets</h2>
            <p className="text-green-500 font-semibold">
              🌿 {result.co2_economise_kg.toFixed(2)} kg de CO² économisés
            </p>
          </div>
          <div className="space-y-4">
            {result.trajets.map((t, i) => (
              <div key={i} className="border border-gray-200 rounded-xl overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2 bg-white border-b border-gray-100">
                  <span className="font-semibold text-sm">{t.voiture}</span>
                  <a href={t.google_maps} target="_blank" rel="noreferrer"
                    className="bg-green-400 text-white px-3 py-1.5 rounded-full text-xs font-medium hover:bg-green-500 flex items-center gap-1">
                    🗺️ Voir trajet
                  </a>
                </div>
                <div className="divide-y divide-gray-100">
                  <div className="px-4 py-3 bg-gray-50">
                    <div className="font-medium text-sm">{t.conducteur}</div>
                    <div className="text-xs text-gray-500">conducteur</div>
                    {t.telephone_conducteur && (
                      <a href={`sms:${t.telephone_conducteur}`} className="text-xs text-green-500 mt-1 block">
                        💬 Envoyer SMS
                      </a>
                    )}
                  </div>
                  {t.passagers.map((p, j) => (
                    <div key={j} className="px-4 py-3 bg-white">
                      <div className="font-medium text-sm">{p.nom}</div>
                      <div className="text-xs text-gray-500">passager</div>
                      {p.telephone && (
                        <a href={`sms:${p.telephone}`} className="text-xs text-green-500 mt-1 block">
                          💬 Envoyer SMS
                        </a>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
          {lastEventId && <SmsLinks trajets={result.trajets} eventId={lastEventId} participantTokens={Object.fromEntries(participants.map(p => [p.name, p.token]))} baseUrl={typeof window !== "undefined" ? window.location.origin : "https://sport-cov.fr"} />}
        </section>
      )}

      {/* Historique événements */}
      {events.length > 0 && (
        <section className="space-y-3 border-t border-gray-100 pt-6">
          <h2 className="text-lg font-semibold">Historique</h2>
          <div className="space-y-2">
            {events.map(ev => (
              <Link key={ev.id} href={`/events/${ev.id}`}
                className="flex items-center justify-between border border-gray-200 rounded-xl px-4 py-3 hover:border-green-400 transition-colors">
                <div>
                  <div className="font-medium text-sm">{ev.title ?? ev.destination}</div>
                  <div className="text-xs text-gray-400">
                    {new Date(ev.created_at).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" })}
                  </div>
                </div>
                <span className="text-gray-400">›</span>
              </Link>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
