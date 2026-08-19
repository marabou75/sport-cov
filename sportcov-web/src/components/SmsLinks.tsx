"use client";

type Passager = { nom: string; telephone?: string };
type Trajet = {
  voiture: string;
  conducteur: string;
  telephone_conducteur?: string;
  passagers: Passager[];
  google_maps: string;
};

type Props = {
  trajets: Trajet[];
  eventId: number;
  participantTokens: Record<string, string>; // name → token
  baseUrl?: string;
};

export default function SmsLinks({ trajets, eventId, participantTokens, baseUrl = "https://sport-cov.fr" }: Props) {
  function playerLink(nom: string) {
    const token = participantTokens[nom];
    if (token) return `${baseUrl}/mon-trajet/${eventId}/${token}`;
    return `${baseUrl}/mon-trajet/${eventId}/${encodeURIComponent(nom)}`; // fallback
  }

  function smsBody(nom: string, voiture: string) {
    return `Bonjour ${nom.split(" ")[0]} ! Voici votre trajet pour ${voiture} : ${playerLink(nom)}`;
  }

  return (
    <div className="space-y-3 mt-4">
      <h3 className="text-sm font-semibold text-gray-600 uppercase tracking-wide">📱 Partager les liens</h3>
      {trajets.map((t, i) => (
        <div key={i} className="border border-gray-200 rounded-xl overflow-hidden">
          <div className="bg-gray-50 px-4 py-2 text-xs font-semibold text-gray-600">{t.voiture}</div>
          <div className="divide-y divide-gray-100">
            {[{ nom: t.conducteur, telephone: t.telephone_conducteur }, ...t.passagers].map((p, j) => (
              <div key={j} className="px-4 py-3 flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="text-sm font-medium truncate">{p.nom}</div>
                  <div className="text-xs text-gray-400 truncate">{playerLink(p.nom)}</div>
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  <button
                    onClick={() => navigator.clipboard.writeText(playerLink(p.nom))}
                    className="text-xs border border-gray-300 px-2 py-1 rounded-full hover:bg-gray-50"
                    title="Copier le lien"
                  >
                    📋
                  </button>
                  {p.telephone && (
                    <a
                      href={`sms:${p.telephone}?body=${encodeURIComponent(smsBody(p.nom, t.voiture))}`}
                      className="text-xs bg-green-400 text-white px-3 py-1 rounded-full hover:bg-green-500"
                    >
                      Envoyer SMS
                    </a>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
