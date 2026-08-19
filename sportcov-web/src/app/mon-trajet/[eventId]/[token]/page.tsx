"use client";
import { useEffect, useState, useRef } from "react";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";

const LiveMap = dynamic(() => import("@/components/LiveMap"), { ssr: false });

const API = process.env.NEXT_PUBLIC_API_URL || "https://api.sport-cov.fr";
const WS_API = API.replace("https://", "wss://").replace("http://", "ws://");

type Passager = { nom: string; telephone: string; marche: boolean };
type TripInfo = {
  voiture: string;
  role: "driver" | "passenger";
  conducteur: string;
  telephone_conducteur: string;
  passagers: Passager[];
  google_maps: string;
  player_name: string;
};
type ChatMsg = { nom: string; msg: string; ts: number };

export default function MonTrajetPage() {
  const { eventId, token } = useParams<{ eventId: string; token: string }>();

  const [trip, setTrip] = useState<TripInfo | null>(null);
  const [error, setError] = useState("");
  const [showMap, setShowMap] = useState(false);
  const [sharingLocation, setSharingLocation] = useState(false);

  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [chatInput, setChatInput] = useState("");
  const chatWsRef = useRef<WebSocket | null>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API}/events/${eventId}/trips/player/${token}`)
      .then(r => { if (!r.ok) throw new Error("Lien invalide ou trajet introuvable"); return r.json(); })
      .then(setTrip)
      .catch(e => setError(e.message));
  }, [eventId, token]);

  useEffect(() => {
    if (!trip) return;
    const voitureKey = encodeURIComponent(trip.voiture);
    const ws = new WebSocket(`${WS_API}/ws/chat/${eventId}/${voitureKey}`);
    chatWsRef.current = ws;
    ws.onmessage = e => {
      const msg: ChatMsg = JSON.parse(e.data);
      setMessages(prev => [...prev, msg]);
      setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    };
    return () => ws.close();
  }, [trip, eventId]);

  function sendMsg(e: React.FormEvent) {
    e.preventDefault();
    if (!chatInput.trim() || !chatWsRef.current || !trip) return;
    chatWsRef.current.send(JSON.stringify({ nom: trip.player_name, msg: chatInput.trim(), ts: Date.now() }));
    setChatInput("");
  }

  if (error) return (
    <div className="text-center py-20 space-y-3">
      <p className="text-4xl">😕</p>
      <p className="text-gray-600">{error}</p>
    </div>
  );
  if (!trip) return <p className="text-gray-400 text-center py-20">Chargement…</p>;

  const wsUrl = `${WS_API}/ws/location/${eventId}/${encodeURIComponent(trip.voiture)}`;
  const isDriver = trip.role === "driver";
  const playerName = trip.player_name;

  return (
    <div className="space-y-6">
      <div className="text-center space-y-1">
        <div className="text-3xl">{isDriver ? "🚗" : "👤"}</div>
        <h1 className="text-xl font-bold">{playerName}</h1>
        <p className="text-sm text-gray-500">{isDriver ? "Vous êtes le conducteur" : "Vous êtes passager"} — {trip.voiture}</p>
      </div>

      <a href={trip.google_maps} target="_blank" rel="noreferrer"
        className="flex items-center justify-center gap-2 bg-green-400 hover:bg-green-500 text-white font-semibold py-3 rounded-full transition-colors">
        📍 Lien Google Maps du trajet
      </a>

      {/* Bouton SMS rappel */}
      {(() => {
        const playerUrl = typeof window !== "undefined" ? window.location.href : "";
        const smsText = `🚗 Rappel covoiturage Sport Cov !\n\n`
          + `Destination : ${trip.voiture}\n`
          + `Conducteur : ${trip.conducteur}\n\n`
          + `📍 Trajet Google Maps :\n${trip.google_maps}\n\n`
          + `📡 Suivi en temps réel + chat voiture :\n${playerUrl}`;
        return (
          <a
            href={`sms:?body=${encodeURIComponent(smsText)}`}
            className="flex items-center justify-center gap-2 border-2 border-green-400 text-green-600 font-semibold py-3 rounded-full transition-colors hover:bg-green-50"
          >
            📱 Partager par SMS
          </a>
        );
      })()}

      <div className="border border-gray-200 rounded-xl overflow-hidden">
        <div className="bg-gray-50 px-4 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">Conducteur</div>
        <div className="px-4 py-4">
          <div className="font-bold text-lg">{trip.conducteur}</div>
          {trip.telephone_conducteur && (
            <div className="mt-2 flex gap-2">
              <a href={`tel:${trip.telephone_conducteur}`}
                className="flex-1 text-center border border-green-400 text-green-500 py-2 rounded-full text-sm font-medium hover:bg-green-50">
                📞 Appeler
              </a>
              <a href={`sms:${trip.telephone_conducteur}`}
                className="flex-1 text-center bg-green-400 text-white py-2 rounded-full text-sm font-medium hover:bg-green-500">
                💬 Envoyer SMS
              </a>
            </div>
          )}
        </div>
      </div>

      {trip.passagers.length > 0 && (
        <div className="border border-gray-200 rounded-xl overflow-hidden">
          <div className="bg-gray-50 px-4 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">
            Passagers ({trip.passagers.length})
          </div>
          <div className="divide-y divide-gray-100">
            {trip.passagers.map((p, i) => (
              <div key={i} className="px-4 py-3 flex items-center justify-between">
                <div>
                  <div className="font-medium">{p.nom}</div>
                  {p.marche && <div className="text-xs text-orange-500">Marche</div>}
                </div>
                {p.telephone && (
                  <a href={`sms:${p.telephone}`}
                    className="bg-green-400 text-white px-3 py-1.5 rounded-full text-xs font-medium hover:bg-green-500">
                    💬 SMS
                  </a>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="border border-gray-200 rounded-xl overflow-hidden">
        <div className="px-4 py-3 flex items-center justify-between">
          <div>
            <div className="font-semibold text-sm">📡 Suivi en temps réel</div>
            <div className="text-xs text-gray-400">
              {isDriver ? "Partagez votre position avec vos passagers" : "Voir la position du chauffeur"}
            </div>
          </div>
          <button
            onClick={() => { setShowMap(!showMap); if (isDriver) setSharingLocation(!sharingLocation); }}
            className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
              showMap ? "bg-red-100 text-red-500 hover:bg-red-200" : "bg-green-400 text-white hover:bg-green-500"
            }`}
          >
            {showMap ? "Arrêter" : isDriver ? "Démarrer" : "Voir la carte"}
          </button>
        </div>
        {showMap && (
          <div className="px-4 pb-4">
            <LiveMap wsUrl={wsUrl} driverName={trip.conducteur} isDriver={isDriver} />
            {isDriver && (
              <p className="text-xs text-gray-400 text-center mt-2">
                🟢 Votre position est partagée avec vos passagers
              </p>
            )}
          </div>
        )}
      </div>

      <div className="border border-gray-200 rounded-xl overflow-hidden">
        <div className="bg-gray-50 px-4 py-2 text-xs font-semibold text-gray-500 uppercase tracking-wide">
          💬 Chat — {trip.voiture}
        </div>
        <div className="px-4 py-3 space-y-2 max-h-48 overflow-y-auto">
          {messages.length === 0 ? (
            <p className="text-gray-400 text-sm text-center py-4">Aucun message pour le moment</p>
          ) : (
            messages.map((m, i) => (
              <div key={i} className={`flex gap-2 ${m.nom === playerName ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[80%] px-3 py-2 rounded-2xl text-sm ${
                  m.nom === playerName ? "bg-green-400 text-white rounded-br-sm" : "bg-gray-100 text-gray-800 rounded-bl-sm"
                }`}>
                  {m.nom !== playerName && <div className="text-xs font-semibold mb-1 opacity-70">{m.nom}</div>}
                  {m.msg}
                </div>
              </div>
            ))
          )}
          <div ref={chatBottomRef} />
        </div>
        <form onSubmit={sendMsg} className="border-t border-gray-100 flex gap-2 px-4 py-3">
          <input
            value={chatInput} onChange={e => setChatInput(e.target.value)}
            placeholder="Écrivez quelque chose…"
            className="flex-1 text-sm outline-none text-gray-700"
          />
          <button type="submit" className="text-green-400 font-bold text-xl">›</button>
        </form>
      </div>
    </div>
  );
}
