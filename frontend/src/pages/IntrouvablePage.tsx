import { Link } from "react-router-dom";

export default function IntrouvablePage() {
  return (
    <div className="contenu-etroit page-erreur">
      <h1>Page introuvable</h1>
      <p>Cette adresse ne correspond à aucune page de l'application.</p>
      <Link className="bouton" to="/planning">
        Retour au planning
      </Link>
    </div>
  );
}
