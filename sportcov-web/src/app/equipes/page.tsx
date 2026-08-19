"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL || "https://api.sport-cov.fr";
type Team = { id: number; name: string; code: string };

export default function EquipesPage() {
  const [teams, setTeams] = useState<Team[]>([]);

  useEffect(() => {
    apiFetch(`${API}/teams`)
      .then(r => r.ok ? r.json() : [])
      .then(data => Array.isArray(data) ? setTeams(data) : null)
      .catch(console.error);
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Mes équipes</h1>
        <Link href="/equipes/new"
          className="bg-green-400 text-white px-4 py-2 rounded-full text-sm font-medium hover:bg-green-500">
          + Nouvelle équipe
        </Link>
      </div>

      {teams.length === 0 ? (
        <div className="text-center py-16 space-y-4">
          <p className="text-4xl">🏃</p>
          <p className="text-gray-500">Aucune équipe pour le moment.</p>
          <Link href="/equipes/new"
            className="inline-block bg-green-400 text-white px-6 py-3 rounded-full font-medium hover:bg-green-500">
            Créer ma première équipe
          </Link>
        </div>
      ) : (
        <div className="space-y-3">
          {teams.map(t => (
            <Link key={t.id} href={`/equipes/${t.id}`}
              className="flex items-center justify-between bg-white border border-gray-200 rounded-xl p-4 hover:border-green-400 transition-colors">
              <div>
                <div className="font-semibold">{t.name}</div>
                <div className="text-xs text-gray-400 mt-0.5">{t.code}</div>
              </div>
              <span className="text-gray-400 text-xl">›</span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
