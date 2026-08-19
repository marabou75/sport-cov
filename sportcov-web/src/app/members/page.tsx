"use client";

import { useEffect, useState } from "react";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "https://api.sport-cov.fr";

type Participant = {
  id: number;
  name: string;
  address: string;
  email?: string | null;
  telephone?: string | null;
};

type Team = { id: number; code: string; name: string };

export default function MembersPage() {
  const [teamId, setTeamId] = useState<number | null>(null);
  const [team, setTeam] = useState<Team | null>(null);
  const [members, setMembers] = useState<Participant[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Champs du nouveau membre
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [street, setStreet] = useState("");
  const [postcode, setPostcode] = useState("");
  const [city, setCity] = useState("");
  const [email, setEmail] = useState("");
  const [telephone, setTelephone] = useState("");
  const [saving, setSaving] = useState(false);

  // 1) Récupérer l’équipe actuelle au chargement
  useEffect(() => {
    if (typeof window === "undefined") return;
    const saved = window.localStorage.getItem("sportcov.currentTeamId");
    if (saved) {
      setTeamId(Number(saved));
    } else {
      setLoading(false);
    }
  }, []);

  // 2) Réagir aux changements d’équipe (event envoyé par AppShell)
  useEffect(() => {
    if (typeof window === "undefined") return;

    const handler = (event: any) => {
      const newId = event.detail?.teamId;
      if (typeof newId === "number" && newId > 0) {
        setTeamId(newId);
      }
    };

    window.addEventListener("sportcov-team-changed", handler);
    return () => window.removeEventListener("sportcov-team-changed", handler);
  }, []);

  // 3) Charger équipe + membres quand teamId change
  useEffect(() => {
    if (!teamId) return;

    async function load() {
      try {
        setLoading(true);
        setError(null);

        const [teamsRes, membersRes] = await Promise.all([
          fetch(`${API_URL}/teams`),
          fetch(`${API_URL}/teams/${teamId}/participants`),
        ]);

        if (!teamsRes.ok) throw new Error(`Teams HTTP ${teamsRes.status}`);
        if (!membersRes.ok)
          throw new Error(`Members HTTP ${membersRes.status}`);

        const teams: Team[] = await teamsRes.json();
        setTeam(teams.find((t) => t.id === teamId) || null);

        const m: Participant[] = await membersRes.json();
        setMembers(m);
      } catch (err: any) {
        console.error(err);
        setError(err.message ?? "Erreur inconnue");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [teamId]);

  // 4) Ajout d’un membre
  async function handleAddMember(e: React.FormEvent) {
    e.preventDefault();
    if (!teamId) return;

    const fn = firstName.trim();
    const ln = lastName.trim();
    const st = street.trim();
    const pc = postcode.trim();
    const ct = city.trim();

    if (!fn || !ln || !st || !pc || !ct) {
      alert(
        "Merci de remplir au minimum prénom, nom, adresse, code postal et ville."
      );
      return;
    }

    const fullName = `${fn} ${ln}`;
    const fullAddress = `${st}, ${pc} ${ct}`;

    setSaving(true);
    try {
      const res = await fetch(`${API_URL}/teams/${teamId}/participants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: fullName,
          address: fullAddress,
          email: email.trim() || null,
          telephone: telephone.trim() || null,
        }),
      });

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }

      const created: Participant = await res.json();
      setMembers((prev) => [...prev, created]);

      // reset formulaire
      setFirstName("");
      setLastName("");
      setStreet("");
      setPostcode("");
      setCity("");
      setEmail("");
      setTelephone("");
    } catch (err: any) {
      console.error(err);
      alert("Erreur lors de l’ajout du membre : " + (err.message ?? ""));
    } finally {
      setSaving(false);
    }
  }

  if (!teamId && !loading) {
    return <p>Choisis d’abord une équipe dans le menu de gauche.</p>;
  }

  if (loading) return <p>Chargement des membres…</p>;
  if (error) return <p className="text-red-600">Erreur : {error}</p>;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">
        Membres de l&apos;équipe {team?.name || ""}
      </h1>

      {!members.length && (
        <p>Aucun membre enregistré pour cette équipe pour le moment.</p>
      )}

      {members.length > 0 && (
        <table className="min-w-full text-sm bg-white border border-slate-200 rounded-lg overflow-hidden mb-6">
          <thead className="bg-slate-100">
            <tr>
              <th className="px-3 py-2 text-left">Nom complet</th>
              <th className="px-3 py-2 text-left">Adresse</th>
              <th className="px-3 py-2 text-left">Email</th>
              <th className="px-3 py-2 text-left">Téléphone</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id} className="border-t border-slate-200">
                <td className="px-3 py-2">{m.name}</td>
                <td className="px-3 py-2">{m.address}</td>
                <td className="px-3 py-2">{m.email}</td>
                <td className="px-3 py-2">{m.telephone}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* Formulaire d’ajout de membre */}
      <form
        onSubmit={handleAddMember}
        className="bg-white border border-slate-200 rounded-lg p-4 space-y-3"
      >
        <h2 className="font-semibold mb-2 text-sm">
          Ajouter un nouveau membre
        </h2>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium mb-1">Prénom *</label>
            <input
              className="w-full rounded border px-2 py-1 text-sm"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Nom *</label>
            <input
              className="w-full rounded border px-2 py-1 text-sm"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
            />
          </div>

          <div className="md:col-span-2">
            <label className="block text-xs font-medium mb-1">
              Adresse (rue, numéro) *
            </label>
            <input
              className="w-full rounded border px-2 py-1 text-sm"
              value={street}
              onChange={(e) => setStreet(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">
              Code postal *
            </label>
            <input
              className="w-full rounded border px-2 py-1 text-sm"
              value={postcode}
              onChange={(e) => setPostcode(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">Ville *</label>
            <input
              className="w-full rounded border px-2 py-1 text-sm"
              value={city}
              onChange={(e) => setCity(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">E-mail</label>
            <input
              type="email"
              className="w-full rounded border px-2 py-1 text-sm"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>

          <div>
            <label className="block text-xs font-medium mb-1">
              Téléphone
            </label>
            <input
              className="w-full rounded border px-2 py-1 text-sm"
              value={telephone}
              onChange={(e) => setTelephone(e.target.value)}
            />
          </div>
        </div>

        <button
          type="submit"
          disabled={saving || !teamId}
          className="mt-2 inline-flex items-center rounded bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60"
        >
          {saving ? "Enregistrement..." : "Ajouter le membre"}
        </button>
      </form>
    </div>
  );
}
