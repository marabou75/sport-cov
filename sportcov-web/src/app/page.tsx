export default function PresentationPage() {
  return (
    <div className="text-center space-y-12">
      <h1 className="text-3xl font-bold mt-4">Présentation de l&apos;application</h1>

      <div className="flex justify-center">
        <img src="/logo.png" alt="Sport Cov" className="h-36 mx-auto" />
      </div>

      <p className="text-gray-700 text-lg max-w-xl mx-auto">
        Utiliser Sport Cov permet de calculer les trajets optimisés avec vos
        coéquipiers et de tirer de nombreux avantages
      </p>

      <div className="space-y-8 text-left max-w-lg mx-auto">
        <div>
          <h2 className="text-2xl font-bold text-center mb-1">Du temps</h2>
          <p className="text-gray-600 text-center">
            Pour les parents, une diminution jusqu&apos;à -75% du nombre de trajets jusqu&apos;au club
          </p>
        </div>
        <div>
          <h2 className="text-2xl font-bold text-center mb-1">De l&apos;argent</h2>
          <p className="text-gray-600 text-center">
            Des économies financières conséquentes en fin de saison
          </p>
        </div>
        <div>
          <h2 className="text-2xl font-bold text-center mb-1">Economie d&apos;énergie</h2>
          <p className="text-gray-600 text-center">
            En moyenne, une économie de 12kg/CO² par entraînement par équipe
          </p>
        </div>
        <div>
          <h2 className="text-2xl font-bold text-center mb-1">Convivialité</h2>
          <p className="text-gray-600 text-center">
            Renforcer les liens entre les membres de votre club
          </p>
        </div>
      </div>
    </div>
  );
}
