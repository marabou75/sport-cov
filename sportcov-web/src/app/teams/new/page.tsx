"use client";

import { useState } from "react";

const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "https://api.sport-cov.fr";

type ParticipantRow = {
  firstName: string;
  lastName: string;
  address: string;
  postalCode: string;
  city: string;
  email: string;
  phone: string;
};

const EMPTY_ROW: ParticipantRow = {
  firstName: "",
  lastName: "",
  address: "",
  postalCode: "",
  city: "",
  email: "",
  phone: "",
};

export default function NewTeamPage() {
  const [teamName, setTeamName] = useState("");
  const [teamCode, setTeamCode] = useState("");
  const [rows, setRows] = useState<ParticipantRow[]>(
    Array.from({ length: 10 }, () => ({ ...EMPTY_ROW })),
  );
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Génère un code équipe simple à partir du nom
  function generateCode(name: string) {
    return name
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 32);
  }

  function handleTeamNameChange(value: string) {
    setTeamName(value);
    if (!teamCode) {
      setTeamCode(generateCode(value));
    }
  }

  function handleCellChange(
    rowIndex: number,
    field: keyof ParticipantRow,
    value: string,
  ) {
    setRows((prev) => {
      const copy = [...prev];
      copy[rowIndex] = { ...copy[rowIndex], [field]: value };
      return copy;
    });
  }

  // Gestion du coller multi-cellules depuis Excel / Google Sheets
  function handlePaste(
    rowIndex: number,
    fieldIndex: number,
    e: React.ClipboardEvent<HTMLInputElement>,
  ) {
    const text = e.clipboardData.getData("text");
    if (!text) return;
    e.preventDefault();

    const lines = text
      .split(/\r?\n/)
      .map((l) => l.trim())
      .filter((l) => l.length > 0);

    if (lines.length === 0) return;

    const fieldOrder: (keyof ParticipantRow)[] = [
      "firstName",
      "lastName",
      "address",
      "postalCode",
      "city",
      "email",
      "phone",
    ];

    setRows((prev) => {
      let data = [...prev];

      // S’assurer d’avoir assez de lignes
      const needed = rowIndex + lines.length;
      if (needed > data.length) {
        const toAdd = needed - data.length;
        for (let i = 0; i < toAdd; i++) data.push({ ...EMPTY_ROW });
      }

      lines.forEach((line, lineIdx) => {
        const cols = line.split("\t");
        const rIndex = rowIndex + lineIdx;
        const existing = data[rIndex] || { ...EMPTY_ROW };
        const updated: ParticipantRow = { ...existing };

        cols.forEach((colVal, colIdx) => {
          const fIndex = fieldIndex + colIdx;
          if (fIndex >= fieldOrder.length) return;
          const field = fieldOrder[fIndex];
          (updated as any)[field] = colVal.trim();
        });

        data[rIndex] = updated;
      });

      return data;
    });
  }

  async function handleSave() {
    setError(null);
    setMessage(null);

    if (!teamName.trim()) {
      setError("Le nom d’équipe est obligatoire.");
      return;
    }
    if (!teamCode.trim()) {
      setError("Le code équipe est obligatoire.");
      return;
    }

    setSaving(true);
    try {
      // 1) Création / mise à jour de l’équipe côté API
      const res = await fetch(`${API_URL}/teams`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          code: teamCode.trim(),
          name: teamName.trim(),
          logo_url: null,
        }),
      });
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}`);
      }
      const team = await res.json();
      const teamId: number = team.id;

      // 2) Construire la liste des participants non vides
      const participantsToCreate = rows
        .map((row) => {
          const firstName = row.firstName.trim();
          const lastName = row.lastName.trim();
          const address = row.address.trim();
          const postalCode = row.postalCode.trim();
          const city = row.city.trim();
          const email = row.email.trim();
          const phone = row.phone.trim();

          // On ignore les lignes vides (pas de nom ni d'adresse)
          if (!firstName && !lastName && !address) {
            return null;
          }

          const fullName = `${firstName} ${lastName}`.trim();

          if (!fullName || !address) {
            // si on a commencé à remplir mais qu'il manque l'essentiel,
            // on peut soit ignorer, soit lever une erreur.
            // Ici on choisit d'ignorer la ligne incomplète.
            return null;
          }

          return {
            name: fullName,
            address,
            postal_code: postalCode || null,
            city: city || null,
            email: email || null,
            telephone: phone || null,
          };
        })
        .filter((p): p is NonNullable<typeof p> => p !== null);

      // 3) Création des participants côté API
      for (const p of participantsToCreate) {
        const resP = await fetch(
          `${API_URL}/teams/${teamId}/participants`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(p),
          },
        );

        if (!resP.ok) {
          console.error(
            "Erreur lors de la création d’un participant :",
            await resP.text(),
          );
          // On ne throw pas pour permettre de continuer les autres,
          // mais on pourrait choisir de stopper tout si tu préfères.
        }
      }

      // 4) Définir cette équipe comme équipe actuelle dans le localStorage
      if (typeof window !== "undefined") {
        window.localStorage.setItem(
          "sportcov.currentTeamId",
          String(teamId),
        );
        window.dispatchEvent(
          new CustomEvent("sportcov-team-changed", {
            detail: { teamId },
          }),
        );
      }

      setMessage(
        `Équipe "${team.name}" créée (id = ${team.id}) avec ${participantsToCreate.length} membre(s).`,
      );
    } catch (e: any) {
      console.error(e);
      setError("Erreur lors de l’enregistrement de l’équipe.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold mb-2">Créer une nouvelle équipe</h1>

      {/* Infos équipe */}
      <div className="bg-white rounded-xl shadow p-4 space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <label className="flex flex-col text-sm">
            Nom de l’équipe *
            <input
              className="mt-1 rounded border px-2 py-1"
              value={teamName}
              onChange={(e) => handleTeamNameChange(e.target.value)}
              placeholder="Ex : FCVDC Seniors"
            />
          </label>

          <label className="flex flex-col text-sm">
            Code équipe (unique) *
            <input
              className="mt-1 rounded border px-2 py-1"
              value={teamCode}
              onChange={(e) => setTeamCode(e.target.value)}
              placeholder="Ex : fcvdc-senior"
            />
          </label>
        </div>
      </div>

      {/* Tableau des membres */}
      <div className="bg-white rounded-xl shadow p-4 space-y-4">
        <div className="bg-sky-50 border border-sky-100 text-xs text-slate-700 rounded-lg p-3">
          <strong>Astuce :</strong> vous pouvez{" "}
          <ul className="list-disc ml-5 mt-1 space-y-0.5">
            <li>remplir le tableau manuellement, ou</li>
            <li>
              copier/coller plusieurs lignes depuis Excel / Google Sheets
              (colonnes dans l’ordre : prénom, nom, adresse, code postal, ville,
              e-mail, téléphone).
            </li>
          </ul>
        </div>

        <div className="overflow-x-auto">
          <table className="min-w-full border text-xs">
            <thead className="bg-slate-100">
              <tr>
                <th className="border px-2 py-1 w-8">#</th>
                <th className="border px-2 py-1">Prénom</th>
                <th className="border px-2 py-1">Nom</th>
                <th className="border px-2 py-1">Adresse</th>
                <th className="border px-2 py-1">Code postal</th>
                <th className="border px-2 py-1">Ville</th>
                <th className="border px-2 py-1">E-mail</th>
                <th className="border px-2 py-1">Téléphone</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  <td className="border px-2 py-1 text-center">
                    {rowIndex + 1}
                  </td>

                  {(
                    [
                      "firstName",
                      "lastName",
                      "address",
                      "postalCode",
                      "city",
                      "email",
                      "phone",
                    ] as (keyof ParticipantRow)[]
                  ).map((field, colIndex) => (
                    <td key={field} className="border px-1 py-0.5">
                      <input
                        className="w-full border-none outline-none px-1 py-0.5 text-xs"
                        value={row[field]}
                        onChange={(e) =>
                          handleCellChange(rowIndex, field, e.target.value)
                        }
                        onPaste={(e) => handlePaste(rowIndex, colIndex, e)}
                      />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <button
          type="button"
          className="mt-3 text-xs rounded border px-3 py-1 hover:bg-slate-100"
          onClick={() =>
            setRows((prev) => [...prev, { ...EMPTY_ROW }, { ...EMPTY_ROW }])
          }
        >
          + Ajouter 2 lignes
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {message && <p className="text-sm text-emerald-700">{message}</p>}

      <button
        type="button"
        onClick={handleSave}
        disabled={saving}
        className="inline-flex items-center rounded bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-60"
      >
        {saving ? "Enregistrement..." : "Enregistrer l’équipe"}
      </button>
    </div>
  );
}
