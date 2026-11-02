import { NavLink, Outlet } from "react-router-dom";
import { useAuth, useUtilisateur } from "../../auth/AuthContext.tsx";
import { Autorise } from "../../auth/RouteProtegee.tsx";
import { LIBELLES_ROLES } from "../../models/index.ts";

/** Squelette des pages connectées : en-tête, navigation selon le rôle, contenu. */
export default function Gabarit() {
  const utilisateur = useUtilisateur();
  const { deconnecter } = useAuth();

  return (
    <div className="app">
      <a className="lien-evitement" href="#contenu">
        Aller au contenu
      </a>
      <header className="entete">
        <p className="marque">
          Réservation de salles <span>IUT</span>
        </p>
        <nav aria-label="Navigation principale">
          <ul>
            <li>
              <NavLink to="/planning">Planning</NavLink>
            </li>
            <Autorise roles={["etudiant", "enseignant"]}>
              <li>
                <NavLink to="/mes-reservations">Mes réservations</NavLink>
              </li>
            </Autorise>
            <Autorise roles={["gestionnaire"]}>
              <li>
                <NavLink to="/gestion/reservations">Suivi et historique</NavLink>
              </li>
              <li>
                <NavLink to="/gestion/salles">Salles</NavLink>
              </li>
              <li>
                <NavLink to="/gestion/utilisateurs">Comptes</NavLink>
              </li>
            </Autorise>
          </ul>
        </nav>
        <div className="compte">
          <span>
            {utilisateur.prenom} {utilisateur.nom}
          </span>
          <span className="jeton-role">{LIBELLES_ROLES[utilisateur.role]}</span>
          <button type="button" className="lien-nu" onClick={() => void deconnecter()}>
            Se déconnecter
          </button>
        </div>
      </header>
      <main id="contenu" className="contenu" tabIndex={-1}>
        <Outlet />
      </main>
    </div>
  );
}
