export default function DashboardPage() {
  return (
    <div className="max-w-5xl mx-auto space-y-8">
      <header>
        <h1 className="text-2xl md:text-3xl font-semibold mb-2">
          Tableau de bord
        </h1>
        <p className="text-slate-600 text-sm">
          Vue d’ensemble des événements, trajets et covoiturages pour l’équipe
          sélectionnée.
        </p>
      </header>

      <section className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs uppercase text-slate-500 mb-1">
            Événements
          </div>
          <div className="text-2xl font-semibold">–</div>
          <div className="text-xs text-slate-500 mt-1">
            Bientôt branché sur /events.
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs uppercase text-slate-500 mb-1">
            Trajets optimisés
          </div>
          <div className="text-2xl font-semibold">–</div>
          <div className="text-xs text-slate-500 mt-1">
            Bientôt branché sur /events/{`{id}`}/trips.
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="text-xs uppercase text-slate-500 mb-1">
            CO₂ économisé
          </div>
          <div className="text-2xl font-semibold">– kg</div>
          <div className="text-xs text-slate-500 mt-1">
            Bientôt calculé à partir de ton API.
          </div>
        </div>
      </section>
    </div>
  );
}
