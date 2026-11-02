/**
 * Planning (A-01 à A-04, A-07 pour les créneaux). Composant « intelligent » :
 * il charge les données, appelle les services et passe le résultat aux
 * composants de présentation (grille, panneau).
 */
import { useCallback, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { messageErreur } from "../api/client.ts";
import { useUtilisateur } from "../auth/AuthContext.tsx";
import Chargement from "../components/commun/Chargement.tsx";
import Message from "../components/commun/Message.tsx";
import EtatDirect from "../components/planning/EtatDirect.tsx";
import GrillePlanning from "../components/planning/GrillePlanning.tsx";
import type { Selection } from "../components/planning/GrillePlanning.tsx";
import PanneauCreneau from "../components/planning/PanneauCreneau.tsx";
import type { Actions } from "../components/planning/PanneauCreneau.tsx";
import SelecteurJour from "../components/planning/SelecteurJour.tsx";
import { usePlanning } from "../hooks/usePlanning.ts";
import { peutReserver } from "../models/index.ts";
import * as reservationService from "../services/reservationService.ts";
import * as salleService from "../services/salleService.ts";
import { aujourdhui, estDateIso, formatHeure, libelleJour, momentIut, premierJourOuvert } from "../utils/dates.ts";
import { construireGrille } from "../utils/grille.ts";

export default function PlanningPage() {
  const utilisateur = useUtilisateur();
  const [parametres, setParametres] = useSearchParams();
  const demande = parametres.get("date") ?? "";
  // La date est dans l'URL : un lien partagé ou une actualisation garde le jour affiché.
  const date = estDateIso(demande) ? demande : premierJourOuvert(aujourdhui());

  const { planning, chargement, erreur, etatDirect, recharger } = usePlanning(date);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [erreurAction, setErreurAction] = useState<string | null>(null);
  const [confirmation, setConfirmation] = useState<string | null>(null);

  // Les cases passées sont calculées à chaque chargement du planning (pas
  // d'horloge qui tourne en arrière-plan) ; l'API refuse de toute façon un
  // créneau déjà commencé.
  const grille = useMemo(() => (planning ? construireGrille(planning, momentIut(new Date())) : null), [planning]);

  const choisirJour = (jour: string) => {
    setSelection(null);
    setParametres({ date: jour });
  };

  const fermerPanneau = useCallback(() => {
    setSelection(null);
    setErreurAction(null);
  }, []);

  const executer = async (action: () => Promise<string>) => {
    setEnvoi(true);
    setErreurAction(null);
    try {
      const texte = await action();
      setSelection(null);
      setConfirmation(texte);
      recharger();
    } catch (cause) {
      setErreurAction(messageErreur(cause));
    } finally {
      setEnvoi(false);
    }
  };

  const actions: Actions = {
    reserver: (heureFin, description) =>
      void executer(async () => {
        if (selection?.type !== "libre") return "";
        await reservationService.reserver({
          salleId: selection.rangee.salle.id,
          date,
          heureDebut: selection.heure,
          heureFin,
          description,
        });
        return `${selection.rangee.salle.code} réservée de ${formatHeure(selection.heure)} à ${formatHeure(heureFin)}.`;
      }),
    fermer: (heureFin, motif) =>
      void executer(async () => {
        if (selection?.type !== "libre") return "";
        const { reservationsAnnulees } = await salleService.fermerCreneau({
          salleId: selection.rangee.salle.id,
          date,
          heureDebut: selection.heure,
          heureFin,
          motif,
        });
        return `Créneau fermé.${reservationsAnnulees ? ` ${reservationsAnnulees} réservation(s) annulée(s).` : ""}`;
      }),
    annuler: (reservationId, motif) =>
      void executer(async () => {
        await reservationService.annuler(reservationId, motif);
        return "Réservation annulée : le créneau est de nouveau libre.";
      }),
    rouvrir: (fermetureId) =>
      void executer(async () => {
        await salleService.rouvrirCreneau(fermetureId);
        return "Créneau rouvert.";
      }),
  };

  return (
    <div className="page-planning">
      <div className="bandeau">
        <div>
          <h1>Planning des salles</h1>
          <p className="discret">{libelleJour(date)}</p>
        </div>
        <div className="rangee-boutons">
          <EtatDirect etat={etatDirect} />
          {/* Repli si le direct est coupé : le planning se recharge à la demande. */}
          <button
            type="button"
            className={etatDirect === "deconnecte" ? "bouton" : "bouton bouton--sobre"}
            onClick={recharger}
            disabled={chargement}
          >
            Rafraîchir
          </button>
        </div>
      </div>

      <SelecteurJour date={date} onChange={choisirJour} />

      {confirmation && (
        <Message type="succes" onFermer={() => setConfirmation(null)}>
          {confirmation}
        </Message>
      )}
      {erreur && <Message type="erreur">{erreur}</Message>}

      {!planning && chargement && <Chargement texte="Chargement du planning…" />}
      {planning && !planning.jourOuvert && <Message type="info">L'IUT est fermé ce jour-là.</Message>}
      {planning &&
        grille &&
        planning.jourOuvert &&
        (grille.rangees.length === 0 ? (
          <p className="vide">Aucune salle n'est proposée à la réservation pour le moment.</p>
        ) : (
          <GrillePlanning
            grille={grille}
            date={date}
            actionCaseLibre={peutReserver(utilisateur.role) ? "Réserver" : "Fermer le créneau"}
            onSelection={(nouvelle) => {
              setErreurAction(null);
              setSelection(nouvelle);
            }}
          />
        ))}

      <ul className="legende" aria-label="Légende">
        <li>
          <i className="puce puce--libre" /> libre
        </li>
        <li>
          <i className="puce puce--mien" /> {peutReserver(utilisateur.role) ? "vos réservations" : "réservé"}
        </li>
        <li>
          <i className="puce puce--occupe" /> réservé
        </li>
        <li>
          <i className="puce puce--fermeture" /> fermé par le gestionnaire
        </li>
        <li>
          <i className="puce puce--passe" /> passé ou hors horaires
        </li>
      </ul>

      {selection && (
        <PanneauCreneau
          key={`${selection.rangee.salle.id}-${selection.type}-${selection.type === "libre" ? selection.heure : ""}`}
          selection={selection}
          date={date}
          utilisateur={utilisateur}
          envoi={envoi}
          erreur={erreurAction}
          actions={actions}
          onFermer={fermerPanneau}
        />
      )}
    </div>
  );
}
