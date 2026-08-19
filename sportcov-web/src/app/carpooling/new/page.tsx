// src/app/carpooling/new/page.tsx
"use client";

import { useEffect, useState } from "react";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "https://api.sport-cov.fr";

type Member = {
  id: number;
  name: string;
  address: string;
  postal_code?: string | null;
  city?: string | null;
  email?: string | null;
  telephone?: string | null;
};

export default function NewCarpoolingPage() {
  const [teamId, setTeamId] = useState<number | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [selectedMemberIds, setSelectedMemberIds] = useState<number[]>([]);
  const [eventAddress, setEventAddress] = useState("");
  const [eventTitle, setEventTitle] = useState("");
  const [isLoadingMembers, setIsLoadingMembers] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Récupération de l'équipe actuelle depuis localStorage
  useEffect(() => {
    const storedTeamId = window.localStorage.getItem("sportcov.currentTeamId");
    if (storedTeamId) {
      setTeamId(Number(storedTeamId));
    }
  }, []);

  // Charger les membres de l’équipe
  useEffect(() => {
    if (!teamId) return;

    const fetchMembers = async () => {
      try {
        setIsLoadingMembers(true);
        setError(null);
        const res = await fetch(`${API_URL}/teams/${teamId}/participants`);
        if (!res.ok) {
          throw new Error("Erreur lors du chargement des membres");
        }
        const data: Member[] = await res.json();
        setMembers(data);
        setSelectedMemberIds(data.map((m) => m.id)); // tous cochés par défaut
      } catch (err: any) {
        console.error(err);
        setError(err.message ?? "Erreur inconnue");
      } finally {
        setIsLoadingMembers(false);
      }
    };

    fetchMembers();
  }, [teamId]);

  const toggleMember = (id: number) => {
    setSelectedMemberIds((prev) =>
      prev.includes(id) ? prev.filter((mId) => mId !== id) : [...prev, id]
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!teamId) {
      setError("Aucune équipe sélectionnée.");
      return;
    }
    if (!eventTitle.trim()) {
      setError("Merci de renseigner le nom de l’événement.");
      return;
    }
    if (!eventAddress.trim()) {
      setError("Merci de renseigner l’adresse de l’événement.");
      return;
    }
    if (selectedMemberIds.length === 0) {
      setError("Merci de sélectionner au moins un membre.");
      return;
    }

    try {
      setIsSubmitting(true);
      setError(null);
      setSuccessMessage(null);

      const res = await fetch(
        `${API_URL}/teams/${teamId}/carpool/optimize`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            event_address: eventAddress,
            participant_ids: selectedMemberIds,
            event_title: eventTitle,
          }),
        }
      );

      if (!res.ok) {
        const text = await res.text();
        throw new Error(
          `Erreur lors de la création des covoiturages : ${text}`
        );
      }

      setSuccessMessage(
        `Covoiturages créés pour l’événement "${eventTitle}".`
      );
    } catch (err: any) {
      console.error(err);
      setError(err.message ?? "Erreur inconnue");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto py-8 px-4">
      <h1 className="text-2xl font-bold mb-4">
        Créer des trajets de covoiturage
      </h1>

      {isLoadingMembers && <p>Chargement des membres…</p>}
      {error && (
        <p className="mb-4 text-red-600 bg-red-50 border border-red-200 p-2 rounded">
          {error}
        </p>
      )}
      {successMessage && (
        <p className="mb-4 text-green-600 bg-green-50 border border-green-200 p-2 rounded">
          {successMessage}
        </p>
      )}

      <form onSubmit={handleSubmit} className="space-y-6">

        {/* Nom de l’événement */}
        <div>
          <label className="block font-medium mb-1">
            Nom de l’événement
          </label>
          <input
            type="text"
            value={eventTitle}
            onChange={(e) => setEventTitle(e.target.value)}
            placeholder="Ex : Match à Tours, Entraînement, Tournoi U15..."
            className="w-full border rounded px-3 py-2"
          />
        </div>

        {/* Adresse de l’événement */}
        <div>
          <label className="block font-medium mb-1">
            Adresse de l’événement
          </label>
          <input
            type="text"
            value={eventAddress}
            onChange={(e) => setEventAddress(e.target.value)}
            placeholder="Ex : 2 Rue de la Gare, 37400 Amboise"
            className="w-full border rounded px-3 py-2"
          />
        </div>

        {/* Liste des membres */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="block font-medium">
              Membres (tous cochés par défaut)
            </label>
            <button
              type="button"
              className="text-sm underline"
              onClick={() =>
                setSelectedMemberIds(members.map((m) => m.id))
              }
            >
              Tout cocher
            </button>
          </div>

          {members.length === 0 ? (
            <p>Aucun membre trouvé pour cette équipe.</p>
          ) : (
            <div className="border rounded p-3 max-h-80 overflow-y-auto space-y-1">
              {members.map((member) => {
                const isChecked = selectedMemberIds.includes(member.id);
                return (
                  <label
                    key={member.id}
                    className="flex items-center gap-2 cursor-pointer"
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleMember(member.id)}
                    />
                    <span>{member.name}</span>
                  </label>
                );
              })}
            </div>
          )}
        </div>

        {/* Bouton de soumission */}
        <div>
          <button
            type="submit"
            disabled={isSubmitting}
            className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-60"
          >
            {isSubmitting ? "Calcul en cours…" : "Calculer les covoiturages"}
          </button>
        </div>
      </form>
    </div>
  );
}
