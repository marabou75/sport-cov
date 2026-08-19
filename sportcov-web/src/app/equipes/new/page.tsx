
"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authHeaders } from "@/lib/auth";

const API = process.env.NEXT_PUBLIC_API_URL || "https://api.sport-cov.fr";

function slugify(s: string) {
  return s.toLowerCase().trim()
    .replace(/[àâä]/g, "a").replace(/[éèêë]/g, "e")
    .replace(/[îï]/g, "i").replace(/[ôö]/g, "o").replace(/[ùûü]/g, "u")
    .replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

export default function NewEquipePage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      const res = await fetch(`${API}/teams`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ name, code: slugify(name) }),
      });
      if (!res.ok) { const d = await res.json(); throw new Error(d.detail || "Erreur"); }
      const team = await res.json();
      router.push(`/equipes/${team.id}`);
    } catch (err: any) { setError(err.message); }
    finally { setLoading(false); }
  }

  return (
    <div className="max-w-md mx-auto space-y-8 py-8">
      <div>
        <h1 className="text-2xl font-bold">Créer une équipe</h1>
        <p className="text-gray-500 text-sm mt-1">Ex : U11-Foot-Amboise, Seniors-Rugby-Tours…</p>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Nom de l&apos;équipe</label>
          <input
            required autoFocus
            value={name} onChange={e => setName(e.target.value)}
            placeholder="U11-Foot-Amboise"
            className="w-full border border-gray-300 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-green-400 focus:ring-1 focus:ring-green-400"
          />
          {name && <p className="text-xs text-gray-400 mt-1">Code : {slugify(name)}</p>}
        </div>
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <button
          type="submit" disabled={loading}
          className="w-full bg-green-400 hover:bg-green-500 text-white font-semibold py-3 rounded-full transition-colors disabled:opacity-60"
        >
          {loading ? "Création…" : "Créer l'équipe →"}
        </button>
      </form>
    </div>
  );
}
