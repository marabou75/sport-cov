// src/lib/mockData.ts

// ---- Types ----
export type Participant = {
  id: string;
  nom: string;
  email: string;
  telephone: string;
  adresse: string;
};

export type Event = {
  id: string;
  nom: string;
  date: string;         // ISO ou texte
  destination: string;
  participantsIds: string[];
};

export type Team = {
  id: string;
  nom: string;
  ville: string;
  categorie: string;
  couleur?: string;
};

export type Co2Stats = {
  totalKg: number;
  trajetsCount: number;
  eventsCount: number;
  lastUpdate: string;
};

// ---- Mocks ----
export const participantsMock: Participant[] = [
  {
    id: "1",
    nom: "Alexis",
    email: "abossard@mail.com",
    telephone: "06 00 00 00 00",
    adresse: "Amboise",
  },
  {
    id: "2",
    nom: "David",
    email: "david@mail.com",
    telephone: "06 00 00 00 00",
    adresse: "Saint-Ouen-les-Vignes",
  },
  {
    id: "3",
    nom: "Andrea",
    email: "andrea@mail.com",
    telephone: "06 00 00 00 00",
    adresse: "Limeray",
  },
];

export const eventsMock: Event[] = [
  {
    id: "match-1",
    nom: "Match FCVDC - Amboise",
    date: "2025-11-20",
    destination: "Stade de l'Île d'Or, 37400 Amboise",
    participantsIds: ["1", "2", "3"],
  },
  {
    id: "entrainement-1",
    nom: "Entraînement du mardi",
    date: "2025-11-25",
    destination: "Stade de l'Île d'Or, 37400 Amboise",
    participantsIds: ["1", "3"],
  },
];

export const teamsMock: Team[] = [
  {
    id: "fcvdc-seniors",
    nom: "FCVDC Seniors",
    ville: "Amboise",
    categorie: "Séniors",
    couleur: "#0f766e",
  },
  {
    id: "fcvdc-u18",
    nom: "FCVDC U18",
    ville: "Amboise",
    categorie: "U18",
    couleur: "#2563eb",
  },
];

export const co2StatsMock: Co2Stats = {
  totalKg: 134.5,
  trajetsCount: 26,
  eventsCount: 8,
  lastUpdate: "2025-11-15",
};
