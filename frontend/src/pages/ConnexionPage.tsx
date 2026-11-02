import { useState } from "react";
import type { FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { messageErreur } from "../api/client.ts";
import { useAuth } from "../auth/AuthContext.tsx";
import { pageAutorisee } from "../auth/acces.ts";
import Message from "../components/commun/Message.tsx";
import type { Role } from "../models/index.ts";

interface EtatNavigation {
  depuis?: { pathname: string; search: string };
}

export default function ConnexionPage() {
  const { connecter, inscrire, erreurDemarrage } = useAuth();
  const navigation = useNavigate();
  const emplacement = useLocation();
  const [inscription, setInscription] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  // Page demandée avant la connexion, si le compte qui se connecte y a droit
  // (après une déconnexion, un autre rôle peut se connecter sur ce poste).
  const destination = (role: Role) => {
    const depuis = (emplacement.state as EtatNavigation | null)?.depuis;
    return depuis && pageAutorisee(depuis.pathname, role) ? depuis.pathname + depuis.search : "/planning";
  };

  const valider = async (evenement: FormEvent<HTMLFormElement>) => {
    evenement.preventDefault();
    const champs = new FormData(evenement.currentTarget);
    const texte = (nom: string) => String(champs.get(nom) ?? "");
    setErreur(null);
    setEnvoi(true);
    try {
      const compte = inscription
        ? await inscrire({
            email: texte("email"),
            motDePasse: texte("mot_de_passe"),
            nom: texte("nom"),
            prenom: texte("prenom"),
          })
        : await connecter(texte("email"), texte("mot_de_passe"));
      navigation(destination(compte.role), { replace: true });
    } catch (cause) {
      setErreur(messageErreur(cause));
      setEnvoi(false);
    }
  };

  return (
    <main className="connexion">
      <form onSubmit={valider} noValidate={false}>
        <div>
          <h1 className="titre">Réservation de salles</h1>
          <p className="discret">IUT · salles de travail</p>
        </div>

        {erreurDemarrage && <Message type="erreur">{erreurDemarrage}</Message>}
        {erreur && <Message type="erreur">{erreur}</Message>}

        {inscription && (
          <div className="grille-champs">
            <div className="champ">
              <label htmlFor="prenom">Prénom</label>
              <input id="prenom" name="prenom" autoComplete="given-name" required maxLength={80} />
            </div>
            <div className="champ">
              <label htmlFor="nom">Nom</label>
              <input id="nom" name="nom" autoComplete="family-name" required maxLength={80} />
            </div>
          </div>
        )}

        <div className="champ">
          <label htmlFor="email">Adresse e-mail universitaire</label>
          <input id="email" name="email" type="email" autoComplete="username" required maxLength={254} />
        </div>
        <div className="champ">
          <label htmlFor="mot_de_passe">Mot de passe</label>
          <input
            id="mot_de_passe"
            name="mot_de_passe"
            type="password"
            autoComplete={inscription ? "new-password" : "current-password"}
            required
            minLength={inscription ? 12 : undefined}
            maxLength={128}
            aria-describedby={inscription ? "aide-mdp" : undefined}
          />
          {inscription && (
            <p id="aide-mdp" className="aide-champ">
              12 caractères minimum. Une phrase facile à retenir fait très bien l'affaire.
            </p>
          )}
        </div>

        <button type="submit" className="bouton" disabled={envoi}>
          {inscription ? "Créer mon compte étudiant" : "Se connecter"}
        </button>

        <p className="aide">
          {inscription ? "Déjà un compte ? " : "Première visite ? "}
          <button
            type="button"
            className="lien-nu"
            onClick={() => {
              setInscription(!inscription);
              setErreur(null);
            }}
          >
            {inscription ? "Se connecter" : "Créer un compte étudiant"}
          </button>
        </p>
      </form>
    </main>
  );
}
