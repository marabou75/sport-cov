"use client";

import { useEffect, useState } from "react";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "https://api.sport-cov.fr";

type Team = {
  id: number;
  code: string;
  name: string;
  logo_url?: string | null;
};

export default function TeamsPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch(`${API_URL}/teams`, {
          credentials: "include",
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: Team[] = await res.json();
        setTeams(data);
      } catch (err: any) {
        console.error(err);
        setError(err.message ?? "Erreur inconnue");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) return <p>Chargement des équipes…</p>;
  if (error) return <p className="text-red-600">Erreur : {error}</p>;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold mb-2">Mes équipes</h1>

      {!teams.length && <p>Aucune équipe pour le moment.</p>}

      <div className="grid gap-3 md:grid-cols-2">
        {teams.map((t) => (
          <div
            key={t.id}
            className="border border-emerald-200 rounded-lg p-3 bg-white shadow-sm"
          >
            <div className="font-semibold">{t.name}</div>
            <div className="text-xs text-slate-500">
              Code : <span className="font-mono">{t.code}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
