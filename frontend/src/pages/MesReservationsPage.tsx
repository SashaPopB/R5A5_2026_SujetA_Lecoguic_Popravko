/** Mes réservations : à venir (annulables, A-05) et historique. */
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { estAnnulation, messageErreur } from "../api/client.ts";
import Chargement from "../components/commun/Chargement.tsx";
import Message from "../components/commun/Message.tsx";
import Pagination from "../components/commun/Pagination.tsx";
import RenduDescription from "../components/texte/RenduDescription.tsx";
import { LIBELLES_STATUTS } from "../models/index.ts";
import type { Page, Reservation } from "../models/index.ts";
import * as reservationService from "../services/reservationService.ts";
import { libelleDateHeure, libelleHeure, libelleJour, momentIut } from "../utils/dates.ts";

type Periode = "a_venir" | "passees";

function LigneReservation({
  reservation,
  onAnnuler,
  envoi,
}: {
  reservation: Reservation;
  onAnnuler?: (reservation: Reservation) => void;
  envoi: boolean;
}) {
  const [confirmation, setConfirmation] = useState(false);
  const annuleeParAutrui = reservation.annuleePar && reservation.annuleePar.id !== reservation.titulaire.id;

  return (
    <li className="ligne">
      <div className="ligne__quand">
        <strong className="heure">
          {libelleHeure(reservation.debut)} – {libelleHeure(reservation.fin)}
        </strong>
        <small className="discret">{libelleJour(momentIut(reservation.debut).date)}</small>
      </div>
      <div className="ligne__quoi">
        <span className="code-salle">{reservation.salle.code}</span>
        <RenduDescription texte={reservation.description} />
        {reservation.statut === "annulee" && reservation.annuleeLe && (
          <small className="discret">
            Annulée le {libelleDateHeure(reservation.annuleeLe)}
            {annuleeParAutrui &&
              reservation.annuleePar &&
              ` par ${reservation.annuleePar.prenom} ${reservation.annuleePar.nom}`}
            {reservation.motifAnnulation && ` : ${reservation.motifAnnulation}`}
          </small>
        )}
      </div>
      <div className="rangee-boutons">
        <span className={`etat etat--${reservation.statut}`}>{LIBELLES_STATUTS[reservation.statut]}</span>
        {onAnnuler &&
          (confirmation ? (
            <>
              <button
                type="button"
                className="bouton bouton--danger"
                disabled={envoi}
                onClick={() => onAnnuler(reservation)}
              >
                Confirmer
              </button>
              <button type="button" className="bouton bouton--sobre" onClick={() => setConfirmation(false)}>
                Non
              </button>
            </>
          ) : (
            <button type="button" className="bouton bouton--danger" onClick={() => setConfirmation(true)}>
              Annuler
            </button>
          ))}
      </div>
    </li>
  );
}

export default function MesReservationsPage() {
  const [parametres, setParametres] = useSearchParams();
  const periode: Periode = parametres.get("periode") === "passees" ? "passees" : "a_venir";
  // La page est dans l'URL, comme la période : un lien ou une actualisation la conserve.
  const page = Math.max(1, Number(parametres.get("page")) || 1);
  const [resultat, setResultat] = useState<Page<Reservation> | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  const charger = useCallback(
    (signal?: AbortSignal) => {
      reservationService
        .mesReservations(periode, page, signal)
        .then((reponse) => {
          setResultat(reponse);
          setErreur(null);
        })
        .catch((cause: unknown) => {
          if (!estAnnulation(cause)) setErreur(messageErreur(cause));
        });
    },
    [periode, page],
  );

  useEffect(() => {
    const controleur = new AbortController();
    setResultat(null);
    charger(controleur.signal);
    return () => controleur.abort();
  }, [charger]);

  const annuler = async (reservation: Reservation) => {
    setEnvoi(true);
    try {
      await reservationService.annuler(reservation.id);
      setSucces(`Réservation de ${reservation.salle.code} annulée.`);
      charger();
    } catch (cause) {
      setErreur(messageErreur(cause));
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <div className="contenu-etroit">
      <div className="bandeau">
        <h1>Mes réservations</h1>
        <Link className="bouton" to="/planning">
          Réserver une salle
        </Link>
      </div>

      <div className="onglets" role="group" aria-label="Période">
        <button type="button" aria-pressed={periode === "a_venir"} onClick={() => setParametres({})}>
          À venir
        </button>
        <button
          type="button"
          aria-pressed={periode === "passees"}
          onClick={() => setParametres({ periode: "passees" })}
        >
          Historique
        </button>
      </div>

      {succes && (
        <Message type="succes" onFermer={() => setSucces(null)}>
          {succes}
        </Message>
      )}
      {erreur && <Message type="erreur">{erreur}</Message>}

      {resultat === null ? (
        <Chargement />
      ) : resultat.elements.length === 0 ? (
        <p className="vide">
          {periode === "a_venir"
            ? "Aucune réservation à venir. Choisissez un créneau libre dans le planning."
            : "Rien dans l'historique pour l'instant."}
        </p>
      ) : (
        <>
          <ul className="liste">
            {resultat.elements.map((reservation) => (
              <LigneReservation
                key={reservation.id}
                reservation={reservation}
                envoi={envoi}
                onAnnuler={periode === "a_venir" ? (r) => void annuler(r) : undefined}
              />
            ))}
          </ul>
          <Pagination
            page={resultat.page}
            taille={resultat.taille}
            total={resultat.total}
            onPage={(numero) =>
              setParametres(periode === "passees" ? { periode, page: String(numero) } : { page: String(numero) })
            }
          />
        </>
      )}
    </div>
  );
}
