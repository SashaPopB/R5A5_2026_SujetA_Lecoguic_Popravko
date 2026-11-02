/**
 * Suivi des réservations, historique (A-08) et export CSV (A-10).
 * Les filtres vivent dans l'URL : la recherche se partage et survit à une
 * actualisation de la page.
 */
import { useEffect, useId, useState } from "react";
import type { FormEvent } from "react";
import { useSearchParams } from "react-router-dom";
import { estAnnulation, messageErreur } from "../api/client.ts";
import Chargement from "../components/commun/Chargement.tsx";
import Message from "../components/commun/Message.tsx";
import Pagination from "../components/commun/Pagination.tsx";
import { LIBELLES_ROLES, LIBELLES_STATUTS } from "../models/index.ts";
import type { Page, Reservation, Salle, StatutReservation } from "../models/index.ts";
import * as reservationService from "../services/reservationService.ts";
import { listerSalles } from "../services/salleService.ts";
import {
  ajouterJours,
  aujourdhui,
  estDateIso,
  libelleDateHeure,
  libelleHeure,
  libelleJour,
  momentIut,
} from "../utils/dates.ts";
import { texteBrut } from "../utils/markdown.ts";

const CHAMPS_FILTRES = ["salle_id", "du", "au", "statut", "recherche"] as const;

function AnnulationEnLigne({ onConfirmer, envoi }: { onConfirmer: (motif?: string) => void; envoi: boolean }) {
  const [ouvert, setOuvert] = useState(false);
  const [motif, setMotif] = useState("");
  const idMotif = useId();
  if (!ouvert) {
    return (
      <button type="button" className="bouton bouton--danger bouton--petit" onClick={() => setOuvert(true)}>
        Annuler
      </button>
    );
  }
  return (
    <div className="confirmation">
      <label htmlFor={idMotif} className="visuellement-cache">
        Motif de l'annulation
      </label>
      <input
        id={idMotif}
        type="text"
        maxLength={200}
        placeholder="Motif (facultatif)"
        value={motif}
        onChange={(e) => setMotif(e.target.value)}
      />
      <button
        type="button"
        className="bouton bouton--danger bouton--petit"
        disabled={envoi}
        onClick={() => onConfirmer(motif.trim() || undefined)}
      >
        Confirmer
      </button>
      <button type="button" className="lien-nu" onClick={() => setOuvert(false)}>
        Non
      </button>
    </div>
  );
}

function ExportCsv() {
  const [du, setDu] = useState(() => `${aujourdhui().slice(0, 8)}01`);
  const [au, setAu] = useState(aujourdhui);
  const valide = estDateIso(du) && estDateIso(au) && du <= au;
  return (
    <section className="carte" aria-labelledby="titre-export">
      <h2 id="titre-export">Exporter pour archivage (CSV)</h2>
      <div className="filtres-ligne">
        <div className="champ champ--compact">
          <label htmlFor="export-du">Du</label>
          <input id="export-du" type="date" value={du} onChange={(e) => setDu(e.target.value)} />
        </div>
        <div className="champ champ--compact">
          <label htmlFor="export-au">Au</label>
          <input id="export-au" type="date" value={au} onChange={(e) => setAu(e.target.value)} />
        </div>
        {valide ? (
          <a className="bouton" href={reservationService.urlExport(du, au)} download>
            Télécharger le CSV
          </a>
        ) : (
          <span className="discret">Choisissez une période valide.</span>
        )}
      </div>
      <p className="aide-champ">Réservations actives et annulées, avec qui a réservé ou annulé et quand.</p>
    </section>
  );
}

export default function GestionReservationsPage() {
  const [parametres, setParametres] = useSearchParams();
  const [salles, setSalles] = useState<Salle[]>([]);
  const [resultat, setResultat] = useState<Page<Reservation> | null>(null);
  const [erreur, setErreur] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [rafraichissement, setRafraichissement] = useState(0);

  const filtres = {
    salleId: parametres.get("salle_id") ?? "",
    du: parametres.get("du") ?? "",
    au: parametres.get("au") ?? "",
    statut: (parametres.get("statut") ?? "") as StatutReservation | "",
    recherche: parametres.get("recherche") ?? "",
    page: Number(parametres.get("page") ?? "1") || 1,
  };
  const cleFiltres = parametres.toString();

  useEffect(() => {
    listerSalles(true)
      .then(setSalles)
      .catch((cause: unknown) => setErreur(messageErreur(cause)));
  }, []);

  useEffect(() => {
    const controleur = new AbortController();
    const courants = new URLSearchParams(cleFiltres);
    reservationService
      .rechercher(
        {
          salleId: courants.get("salle_id") || undefined,
          du: courants.get("du") || undefined,
          au: courants.get("au") || undefined,
          statut: (courants.get("statut") || undefined) as StatutReservation | undefined,
          recherche: courants.get("recherche") || undefined,
          page: Number(courants.get("page") ?? "1") || 1,
        },
        controleur.signal,
      )
      .then((page) => {
        setResultat(page);
        setErreur(null);
      })
      .catch((cause: unknown) => {
        if (!estAnnulation(cause)) setErreur(messageErreur(cause));
      });
    return () => controleur.abort();
  }, [cleFiltres, rafraichissement]);

  const appliquerFiltres = (evenement: FormEvent<HTMLFormElement>) => {
    evenement.preventDefault();
    const donnees = new FormData(evenement.currentTarget);
    const suivants = new URLSearchParams();
    for (const champ of CHAMPS_FILTRES) {
      const valeur = String(donnees.get(champ) ?? "").trim();
      if (valeur) suivants.set(champ, valeur);
    }
    setParametres(suivants);
  };

  const changerPage = (page: number) => {
    const suivants = new URLSearchParams(parametres);
    suivants.set("page", String(page));
    setParametres(suivants);
  };

  const annuler = async (reservation: Reservation, motif?: string) => {
    setEnvoi(true);
    try {
      await reservationService.annuler(reservation.id, motif);
      setSucces(`Réservation de ${reservation.titulaire.prenom} ${reservation.titulaire.nom} annulée.`);
      setRafraichissement((valeur) => valeur + 1);
    } catch (cause) {
      setErreur(messageErreur(cause));
    } finally {
      setEnvoi(false);
    }
  };

  const maintenant = new Date();

  return (
    <div>
      <div className="bandeau">
        <h1>Suivi et historique des réservations</h1>
      </div>

      <form className="carte filtres-ligne" onSubmit={appliquerFiltres} key={cleFiltres}>
        <div className="champ champ--compact">
          <label htmlFor="f-salle">Salle</label>
          <select id="f-salle" name="salle_id" defaultValue={filtres.salleId}>
            <option value="">Toutes</option>
            {salles.map((salle) => (
              <option key={salle.id} value={salle.id}>
                {salle.code}
                {salle.etat === "retiree" ? " (retirée)" : ""}
              </option>
            ))}
          </select>
        </div>
        <div className="champ champ--compact">
          <label htmlFor="f-du">Du</label>
          <input id="f-du" name="du" type="date" defaultValue={filtres.du} />
        </div>
        <div className="champ champ--compact">
          <label htmlFor="f-au">Au</label>
          <input id="f-au" name="au" type="date" defaultValue={filtres.au} />
        </div>
        <div className="champ champ--compact">
          <label htmlFor="f-statut">Statut</label>
          <select id="f-statut" name="statut" defaultValue={filtres.statut}>
            <option value="">Tous</option>
            <option value="active">Actives</option>
            <option value="annulee">Annulées</option>
          </select>
        </div>
        <div className="champ champ--compact">
          <label htmlFor="f-recherche">Personne (nom ou e-mail)</label>
          <input id="f-recherche" name="recherche" type="search" maxLength={80} defaultValue={filtres.recherche} />
        </div>
        <div className="rangee-boutons">
          <button type="submit" className="bouton">
            Filtrer
          </button>
          <button
            type="button"
            className="bouton bouton--sobre"
            onClick={() => setParametres({ du: aujourdhui(), au: ajouterJours(aujourdhui(), 6) })}
          >
            7 prochains jours
          </button>
        </div>
      </form>

      {succes && (
        <Message type="succes" onFermer={() => setSucces(null)}>
          {succes}
        </Message>
      )}
      {erreur && <Message type="erreur">{erreur}</Message>}

      {resultat === null ? (
        <Chargement />
      ) : resultat.elements.length === 0 ? (
        <p className="vide">Aucune réservation ne correspond à ces critères.</p>
      ) : (
        <>
          <p className="discret">{resultat.total} réservation(s)</p>
          <div className="cadre-tableau">
            <table className="tableau">
              <caption className="visuellement-cache">Réservations correspondant aux filtres</caption>
              <thead>
                <tr>
                  <th scope="col">Salle</th>
                  <th scope="col">Créneau</th>
                  <th scope="col">Réservé par</th>
                  <th scope="col">Réservé le</th>
                  <th scope="col">Statut</th>
                  <th scope="col">Annulation</th>
                  <th scope="col">
                    <span className="visuellement-cache">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {resultat.elements.map((reservation) => (
                  <tr key={reservation.id}>
                    <td className="code-salle">{reservation.salle.code}</td>
                    <td>
                      {libelleJour(momentIut(reservation.debut).date)}
                      <br />
                      <span className="heure">
                        {libelleHeure(reservation.debut)} – {libelleHeure(reservation.fin)}
                      </span>
                      <br />
                      <small className="discret">{texteBrut(reservation.description).slice(0, 80)}</small>
                    </td>
                    <td>
                      {reservation.titulaire.prenom} {reservation.titulaire.nom}
                      <br />
                      <small className="discret">
                        {reservation.titulaire.email} · {LIBELLES_ROLES[reservation.titulaire.role]}
                      </small>
                    </td>
                    <td>{libelleDateHeure(reservation.creeLe)}</td>
                    <td>
                      <span className={`etat etat--${reservation.statut}`}>{LIBELLES_STATUTS[reservation.statut]}</span>
                    </td>
                    <td>
                      {reservation.annuleeLe && reservation.annuleePar ? (
                        <>
                          {libelleDateHeure(reservation.annuleeLe)}
                          <br />
                          <small className="discret">
                            par {reservation.annuleePar.prenom} {reservation.annuleePar.nom}
                            {reservation.motifAnnulation && ` : ${reservation.motifAnnulation}`}
                          </small>
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>
                      {reservation.statut === "active" && reservation.fin > maintenant && (
                        <AnnulationEnLigne envoi={envoi} onConfirmer={(motif) => void annuler(reservation, motif)} />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Pagination page={resultat.page} taille={resultat.taille} total={resultat.total} onPage={changerPage} />
        </>
      )}

      <ExportCsv />
    </div>
  );
}
