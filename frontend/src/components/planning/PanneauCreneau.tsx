/**
 * Détail d'une case du planning et actions possibles selon le rôle.
 * Composant de présentation : les appels à l'API sont faits par la page.
 */
import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { DUREE_MAX_ETUDIANT_HEURES } from "../../config.ts";
import { peutReserver } from "../../models/index.ts";
import type { Utilisateur } from "../../models/index.ts";
import { formatHeure, libelleDateHeure, libelleHeure, libelleJour } from "../../utils/dates.ts";
import { heuresDeFinFermeture, heuresDeFinPossibles } from "../../utils/grille.ts";
import Message from "../commun/Message.tsx";
import PanneauLateral from "../commun/PanneauLateral.tsx";
import EditeurDescription from "../texte/EditeurDescription.tsx";
import RenduDescription from "../texte/RenduDescription.tsx";
import type { Selection } from "./GrillePlanning.tsx";

export interface Actions {
  reserver: (heureFin: number, description: string) => void;
  fermer: (heureFin: number, motif: string) => void;
  annuler: (reservationId: string, motif?: string) => void;
  rouvrir: (fermetureId: string) => void;
}

interface Props {
  selection: Selection;
  date: string;
  utilisateur: Utilisateur;
  envoi: boolean;
  erreur: string | null;
  actions: Actions;
  onFermer: () => void;
}

function FormulaireReservation({
  selection,
  utilisateur,
  envoi,
  actions,
}: {
  selection: Extract<Selection, { type: "libre" }>;
  utilisateur: Utilisateur;
  envoi: boolean;
  actions: Actions;
}) {
  const estEtudiant = utilisateur.role === "etudiant";
  const fins = heuresDeFinPossibles(
    selection.rangee,
    selection.heure,
    estEtudiant ? DUREE_MAX_ETUDIANT_HEURES : undefined,
  );
  const [heureFin, setHeureFin] = useState(fins[0] ?? selection.heure + 1);
  const [description, setDescription] = useState("");

  const envoyer = (evenement: FormEvent) => {
    evenement.preventDefault();
    actions.reserver(heureFin, description);
  };

  return (
    <form className="formulaire" onSubmit={envoyer}>
      <div className="champ">
        <label htmlFor="heure-fin">Jusqu'à</label>
        <select id="heure-fin" value={heureFin} onChange={(e) => setHeureFin(Number(e.target.value))}>
          {fins.map((fin) => (
            <option key={fin} value={fin}>
              {formatHeure(fin)} ({fin - selection.heure} h)
            </option>
          ))}
        </select>
        {estEtudiant && (
          <p className="aide-champ">
            {DUREE_MAX_ETUDIANT_HEURES} heures maximum d'affilée, en comptant vos réservations qui se suivent.
          </p>
        )}
      </div>
      <EditeurDescription
        libelle="Ce que vous allez y faire"
        valeur={description}
        onChange={setDescription}
        desactive={envoi}
      />
      <button type="submit" className="bouton" disabled={envoi || description.trim() === ""}>
        Réserver {selection.rangee.salle.code}
      </button>
    </form>
  );
}

function FormulaireFermeture({
  selection,
  envoi,
  actions,
}: {
  selection: Extract<Selection, { type: "libre" }>;
  envoi: boolean;
  actions: Actions;
}) {
  const fins = heuresDeFinFermeture(selection.rangee, selection.heure);
  const [heureFin, setHeureFin] = useState(fins[0] ?? selection.heure + 1);
  const [motif, setMotif] = useState("");
  const reservationsCouvertes = selection.rangee.segments.filter(
    (s) => s.type === "reservation" && s.heure < heureFin && s.heure + s.duree > selection.heure,
  ).length;

  const envoyer = (evenement: FormEvent) => {
    evenement.preventDefault();
    actions.fermer(heureFin, motif);
  };

  return (
    <form className="formulaire" onSubmit={envoyer}>
      <p>Fermer ce créneau le rend indisponible à la réservation.</p>
      <div className="champ">
        <label htmlFor="fin-fermeture">Jusqu'à</label>
        <select id="fin-fermeture" value={heureFin} onChange={(e) => setHeureFin(Number(e.target.value))}>
          {fins.map((fin) => (
            <option key={fin} value={fin}>
              {formatHeure(fin)}
            </option>
          ))}
        </select>
      </div>
      <div className="champ">
        <label htmlFor="motif-fermeture">Motif (affiché dans le planning)</label>
        <input
          id="motif-fermeture"
          type="text"
          required
          maxLength={200}
          value={motif}
          onChange={(e) => setMotif(e.target.value)}
        />
      </div>
      {reservationsCouvertes > 0 && (
        <Message type="info">
          {reservationsCouvertes} réservation(s) sur cette plage seront annulées, avec ce motif.
        </Message>
      )}
      <button type="submit" className="bouton" disabled={envoi || motif.trim() === ""}>
        Fermer le créneau
      </button>
    </form>
  );
}

function DetailReservation({
  selection,
  date,
  utilisateur,
  envoi,
  actions,
}: {
  selection: Extract<Selection, { type: "reservation" }>;
  date: string;
  utilisateur: Utilisateur;
  envoi: boolean;
  actions: Actions;
}) {
  const { reservation, rangee } = selection;
  const estGestionnaire = utilisateur.role === "gestionnaire";
  const peutAnnuler = reservation.estAMoi || estGestionnaire;
  const [confirmation, setConfirmation] = useState(false);
  const [motif, setMotif] = useState("");

  return (
    <div className="formulaire">
      <dl className="recap">
        <dt>Horaire</dt>
        <dd className="heure">
          {libelleHeure(reservation.debut)} – {libelleHeure(reservation.fin)}
        </dd>
        <dt>Réservé par</dt>
        <dd>
          {reservation.estAMoi
            ? "vous"
            : reservation.titulaire
              ? `${reservation.titulaire.prenom} ${reservation.titulaire.nom} (${reservation.titulaire.email})`
              : "information réservée au titulaire et au gestionnaire"}
        </dd>
      </dl>

      {reservation.description !== null && <RenduDescription texte={reservation.description} />}

      {estGestionnaire && (
        <Link to={`/gestion/reservations?${new URLSearchParams({ salle_id: rangee.salle.id, du: date, au: date })}`}>
          Historique de cette salle ce jour-là
        </Link>
      )}

      {peutAnnuler &&
        (confirmation ? (
          <div className="confirmation">
            {estGestionnaire && !reservation.estAMoi && (
              <div className="champ">
                <label htmlFor="motif-annulation">Motif (visible par le titulaire)</label>
                <input
                  id="motif-annulation"
                  type="text"
                  maxLength={200}
                  value={motif}
                  onChange={(e) => setMotif(e.target.value)}
                />
              </div>
            )}
            <div className="rangee-boutons">
              <button
                type="button"
                className="bouton bouton--danger"
                disabled={envoi}
                onClick={() => actions.annuler(reservation.id, motif.trim() || undefined)}
              >
                Confirmer l'annulation
              </button>
              <button type="button" className="bouton bouton--sobre" onClick={() => setConfirmation(false)}>
                Garder la réservation
              </button>
            </div>
          </div>
        ) : (
          <button type="button" className="bouton bouton--danger" onClick={() => setConfirmation(true)}>
            Annuler la réservation
          </button>
        ))}
    </div>
  );
}

function DetailFermeture({
  selection,
  utilisateur,
  envoi,
  actions,
}: {
  selection: Extract<Selection, { type: "fermeture" }>;
  utilisateur: Utilisateur;
  envoi: boolean;
  actions: Actions;
}) {
  const { fermeture } = selection;
  return (
    <div className="formulaire">
      <dl className="recap">
        <dt>Motif</dt>
        <dd>{fermeture.motif}</dd>
        <dt>Du</dt>
        <dd>{libelleDateHeure(fermeture.debut)}</dd>
        <dt>Au</dt>
        <dd>{libelleDateHeure(fermeture.fin)}</dd>
      </dl>
      {utilisateur.role === "gestionnaire" && (
        <button type="button" className="bouton" disabled={envoi} onClick={() => actions.rouvrir(fermeture.id)}>
          Rouvrir ce créneau
        </button>
      )}
    </div>
  );
}

export default function PanneauCreneau({ selection, date, utilisateur, envoi, erreur, actions, onFermer }: Props) {
  const salle = selection.rangee.salle;
  const sousTitre = `${libelleJour(date)} · bâtiment ${salle.batiment.code}, niveau ${salle.etage} · ${salle.capacite} places`;
  const titre =
    selection.type === "libre"
      ? `${salle.code} · ${formatHeure(selection.heure)}`
      : selection.type === "reservation"
        ? `${salle.code} · réservée`
        : `${salle.code} · créneau fermé`;

  return (
    <PanneauLateral titre={titre} sousTitre={sousTitre} onFermer={onFermer}>
      {erreur && <Message type="erreur">{erreur}</Message>}
      {selection.type === "libre" &&
        (peutReserver(utilisateur.role) ? (
          <FormulaireReservation selection={selection} utilisateur={utilisateur} envoi={envoi} actions={actions} />
        ) : (
          <FormulaireFermeture selection={selection} envoi={envoi} actions={actions} />
        ))}
      {selection.type === "reservation" && (
        <DetailReservation
          selection={selection}
          date={date}
          utilisateur={utilisateur}
          envoi={envoi}
          actions={actions}
        />
      )}
      {selection.type === "fermeture" && (
        <DetailFermeture selection={selection} utilisateur={utilisateur} envoi={envoi} actions={actions} />
      )}
    </PanneauLateral>
  );
}
