import { Link } from "react-router-dom";

export default function AccesRefusePage() {
  return (
    <div className="contenu-etroit page-erreur">
      <h1>Accès refusé</h1>
      <p>Cette page est réservée à un autre rôle que le vôtre.</p>
      <Link className="bouton" to="/planning">
        Retour au planning
      </Link>
    </div>
  );
}
