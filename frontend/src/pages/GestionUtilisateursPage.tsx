/** Comptes : le gestionnaire attribue les rôles enseignant et gestionnaire. */
import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { estAnnulation, messageErreur } from "../api/client.ts";
import { useUtilisateur } from "../auth/AuthContext.tsx";
import Chargement from "../components/commun/Chargement.tsx";
import Message from "../components/commun/Message.tsx";
import Pagination from "../components/commun/Pagination.tsx";
import { LIBELLES_ROLES } from "../models/index.ts";
import type { Page, Role, Utilisateur } from "../models/index.ts";
import { changerRole, rechercherUtilisateurs } from "../services/utilisateurService.ts";

const ROLES: Role[] = ["etudiant", "enseignant", "gestionnaire"];

export default function GestionUtilisateursPage() {
  const moi = useUtilisateur();
  const [recherche, setRecherche] = useState("");
  const [page, setPage] = useState(1);
  const [resultat, setResultat] = useState<Page<Utilisateur> | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);

  useEffect(() => {
    const controleur = new AbortController();
    rechercherUtilisateurs(recherche, page, controleur.signal)
      .then(setResultat)
      .catch((cause: unknown) => {
        if (!estAnnulation(cause)) setErreur(messageErreur(cause));
      });
    return () => controleur.abort();
  }, [recherche, page]);

  const chercher = (evenement: FormEvent<HTMLFormElement>) => {
    evenement.preventDefault();
    setPage(1);
    setRecherche(String(new FormData(evenement.currentTarget).get("recherche") ?? ""));
  };

  const modifierRole = async (utilisateur: Utilisateur, role: Role) => {
    try {
      const modifie = await changerRole(utilisateur.id, role);
      setSucces(`${modifie.prenom} ${modifie.nom} est maintenant ${LIBELLES_ROLES[modifie.role].toLowerCase()}.`);
      setResultat(
        (courant) =>
          courant && { ...courant, elements: courant.elements.map((u) => (u.id === modifie.id ? modifie : u)) },
      );
    } catch (cause) {
      setErreur(messageErreur(cause));
    }
  };

  return (
    <div className="contenu-etroit">
      <div className="bandeau">
        <h1>Comptes</h1>
      </div>
      <p className="discret">
        L'inscription crée toujours un compte étudiant. Les rôles enseignant et gestionnaire s'attribuent ici.
      </p>

      <form className="filtres-ligne" onSubmit={chercher} role="search">
        <div className="champ champ--compact">
          <label htmlFor="u-recherche">Nom ou e-mail</label>
          <input id="u-recherche" name="recherche" type="search" maxLength={80} defaultValue={recherche} />
        </div>
        <button type="submit" className="bouton">
          Rechercher
        </button>
      </form>

      {succes && (
        <Message type="succes" onFermer={() => setSucces(null)}>
          {succes}
        </Message>
      )}
      {erreur && (
        <Message type="erreur" onFermer={() => setErreur(null)}>
          {erreur}
        </Message>
      )}

      {resultat === null ? (
        <Chargement />
      ) : (
        <>
          <table className="tableau">
            <caption className="visuellement-cache">Comptes utilisateurs</caption>
            <thead>
              <tr>
                <th scope="col">Nom</th>
                <th scope="col">E-mail</th>
                <th scope="col">Rôle</th>
              </tr>
            </thead>
            <tbody>
              {resultat.elements.map((utilisateur) => (
                <tr key={utilisateur.id}>
                  <th scope="row">
                    {utilisateur.prenom} {utilisateur.nom}
                  </th>
                  <td>{utilisateur.email}</td>
                  <td>
                    {utilisateur.id === moi.id ? (
                      LIBELLES_ROLES[utilisateur.role]
                    ) : (
                      <select
                        aria-label={`Rôle de ${utilisateur.prenom} ${utilisateur.nom}`}
                        value={utilisateur.role}
                        onChange={(e) => void modifierRole(utilisateur, e.target.value as Role)}
                      >
                        {ROLES.map((role) => (
                          <option key={role} value={role}>
                            {LIBELLES_ROLES[role]}
                          </option>
                        ))}
                      </select>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <Pagination page={resultat.page} taille={resultat.taille} total={resultat.total} onPage={setPage} />
        </>
      )}
    </div>
  );
}
