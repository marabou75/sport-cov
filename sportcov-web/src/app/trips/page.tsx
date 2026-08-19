export default function TripsPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-semibold mb-2">
            Mes trajets
          </h1>
          <p className="text-slate-600 text-sm">
            Liste des voitures, conducteurs et passagers pour les événements
            sélectionnés.
          </p>
        </div>
      </header>

      <div className="rounded-xl border border-dashed border-slate-300 bg-white/60 p-6 text-sm text-slate-500">
        Bientôt : cette page affichera les trajets renvoyés par l’API
        <code className="px-1 py-0.5 mx-1 rounded bg-slate-100 text-[11px]">
          /events/&#123;id&#125;/trips
        </code>
        avec le détail par voiture (conducteur, passagers, lien Google Maps,
        etc.).
      </div>
    </div>
  );
}
