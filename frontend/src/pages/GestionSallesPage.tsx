/** Administration des salles (A-07) : créer, modifier, ouvrir, fermer, retirer. */
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { estAnnulation, messageErreur } from "../api/client.ts";
import Chargement from "../components/commun/Chargement.tsx";
import Message from "../components/commun/Message.tsx";
import PanneauLateral from "../components/commun/PanneauLateral.tsx";
import { LIBELLES_ETATS } from "../models/index.ts";
import type { Batiment, EtatSalle, Salle } from "../models/index.ts";
import * as salleService from "../services/salleService.ts";
import type { DonneesSalle } from "../services/salleService.ts";
import { formatHeure } from "../utils/dates.ts";

const HEURES = Array.from({ length: 18 }, (_, i) => i + 6); // 06:00 -> 23:00

const ACTIONS_ETAT: { etat: EtatSalle; libelle: string; avertissement: string }[] = [
  { etat: "ouverte", libelle: "Ouvrir", avertissement: "" },
  { etat: "fermee", libelle: "Fermer", avertissement: "Les réservations à venir de cette salle seront annulées." },
  {
    etat: "retiree",
    libelle: "Retirer",
    avertissement: "La salle quitte le planning ; ses réservations à venir seront annulées. L'historique est conservé.",
  },
];

function FormulaireSalle({
  salle,
  batiments,
  envoi,
  onValider,
}: {
  salle: Salle | null;
  batiments: Batiment[];
  envoi: boolean;
  onValider: (donnees: DonneesSalle) => void;
}) {
  const envoyer = (evenement: FormEvent<HTMLFormElement>) => {
    evenement.preventDefault();
    const champs = new FormData(evenement.currentTarget);
    const texte = (nom: string) => String(champs.get(nom) ?? "").trim();
    const donnees: DonneesSalle = {
      nom: texte("nom") || null,
      batimentId: texte("batiment"),
      etage: Number(texte("etage")),
      capacite: Number(texte("capacite")),
      heureOuverture: Number(texte("ouverture")),
      heureFermeture: Number(texte("fermeture")),
    };
    if (!salle) donnees.code = texte("code");
    onValider(donnees);
  };

  return (
    <form className="formulaire" onSubmit={envoyer}>
      {!salle && (
        <div className="champ">
          <label htmlFor="s-code">Code (affiché sur la porte)</label>
          <input id="s-code" name="code" required maxLength={20} pattern="[A-Za-z0-9][A-Za-z0-9\-]{0,19}" />
        </div>
      )}
      <div className="champ">
        <label htmlFor="s-nom">Nom d'usage (facultatif)</label>
        <input id="s-nom" name="nom" maxLength={80} defaultValue={salle?.nom ?? ""} />
      </div>
      <div className="champ">
        <label htmlFor="s-batiment">Bâtiment</label>
        <select id="s-batiment" name="batiment" required defaultValue={salle?.batiment.id ?? batiments[0]?.id}>
          {batiments.map((batiment) => (
            <option key={batiment.id} value={batiment.id}>
              {batiment.code} – {batiment.nom}
            </option>
          ))}
        </select>
      </div>
      <div className="grille-champs">
        <div className="champ">
          <label htmlFor="s-etage">Étage</label>
          <input id="s-etage" name="etage" type="number" min={-5} max={50} required defaultValue={salle?.etage ?? 0} />
        </div>
        <div className="champ">
          <label htmlFor="s-capacite">Capacité</label>
          <input
            id="s-capacite"
            name="capacite"
            type="number"
            min={1}
            max={500}
            required
            defaultValue={salle?.capacite ?? 8}
          />
        </div>
        <div className="champ">
          <label htmlFor="s-ouverture">Ouverture</label>
          <select id="s-ouverture" name="ouverture" defaultValue={salle?.heureOuverture ?? 8}>
            {HEURES.slice(0, -1).map((heure) => (
              <option key={heure} value={heure}>
                {formatHeure(heure)}
              </option>
            ))}
          </select>
        </div>
        <div className="champ">
          <label htmlFor="s-fermeture">Fermeture</label>
          <select id="s-fermeture" name="fermeture" defaultValue={salle?.heureFermeture ?? 20}>
            {HEURES.slice(1).map((heure) => (
              <option key={heure} value={heure}>
                {formatHeure(heure)}
              </option>
            ))}
          </select>
        </div>
      </div>
      {salle && <p className="aide-champ">Réduire les horaires annule les réservations à venir qui en sortiraient.</p>}
      <button type="submit" className="bouton" disabled={envoi}>
        {salle ? "Enregistrer" : "Créer la salle"}
      </button>
    </form>
  );
}

function ChangementEtat({
  salle,
  envoi,
  onChanger,
}: {
  salle: Salle;
  envoi: boolean;
  onChanger: (etat: EtatSalle) => void;
}) {
  const [demande, setDemande] = useState<(typeof ACTIONS_ETAT)[number] | null>(null);
  const actions = ACTIONS_ETAT.filter((action) => action.etat !== salle.etat);

  if (demande) {
    const aVenir = salle.reservationsAVenir ?? 0;
    return (
      <div className="confirmation">
        <span>
          {demande.libelle} {salle.code} ?{" "}
          {demande.avertissement && aVenir > 0 && (
            <strong>
              {demande.avertissement} ({aVenir})
            </strong>
          )}
        </span>
        <button
          type="button"
          className="bouton bouton--danger bouton--petit"
          disabled={envoi}
          onClick={() => onChanger(demande.etat)}
        >
          Confirmer
        </button>
        <button type="button" className="lien-nu" onClick={() => setDemande(null)}>
          Non
        </button>
      </div>
    );
  }
  return (
    <div className="rangee-boutons">
      {actions.map((action) => (
        <button
          key={action.etat}
          type="button"
          className="bouton bouton--sobre bouton--petit"
          onClick={() => setDemande(action)}
        >
          {action.libelle}
        </button>
      ))}
    </div>
  );
}

export default function GestionSallesPage() {
  const [salles, setSalles] = useState<Salle[] | null>(null);
  const [batiments, setBatiments] = useState<Batiment[]>([]);
  const [edition, setEdition] = useState<Salle | "nouvelle" | null>(null);
  const [envoi, setEnvoi] = useState(false);
  const [erreur, setErreur] = useState<string | null>(null);
  const [erreurFormulaire, setErreurFormulaire] = useState<string | null>(null);
  const [succes, setSucces] = useState<string | null>(null);

  const charger = useCallback((signal?: AbortSignal) => {
    salleService
      .listerSalles(true, signal)
      .then(setSalles)
      .catch((cause: unknown) => {
        if (!estAnnulation(cause)) setErreur(messageErreur(cause));
      });
  }, []);

  useEffect(() => {
    const controleur = new AbortController();
    charger(controleur.signal);
    salleService
      .listerBatiments()
      .then(setBatiments)
      .catch((cause: unknown) => setErreur(messageErreur(cause)));
    return () => controleur.abort();
  }, [charger]);

  const enregistrer = async (donnees: DonneesSalle) => {
    setEnvoi(true);
    setErreurFormulaire(null);
    try {
      if (edition === "nouvelle") {
        const salle = await salleService.creerSalle(donnees);
        setSucces(`Salle ${salle.code} créée.`);
      } else if (edition) {
        const { salle, reservationsAnnulees } = await salleService.modifierSalle(edition.id, donnees);
        setSucces(
          `Salle ${salle.code} modifiée.${reservationsAnnulees ? ` ${reservationsAnnulees} réservation(s) annulée(s).` : ""}`,
        );
      }
      setEdition(null);
      charger();
    } catch (cause) {
      setErreurFormulaire(messageErreur(cause));
    } finally {
      setEnvoi(false);
    }
  };

  const changerEtat = async (salle: Salle, etat: EtatSalle) => {
    setEnvoi(true);
    try {
      const resultat = await salleService.modifierSalle(salle.id, { etat });
      const annulees = resultat.reservationsAnnulees;
      setSucces(
        `${salle.code} : ${LIBELLES_ETATS[etat].toLowerCase()}.${annulees ? ` ${annulees} réservation(s) annulée(s).` : ""}`,
      );
      charger();
    } catch (cause) {
      setErreur(messageErreur(cause));
    } finally {
      setEnvoi(false);
    }
  };

  return (
    <div>
      <div className="bandeau">
        <h1>Salles</h1>
        <button type="button" className="bouton" onClick={() => setEdition("nouvelle")}>
          Ajouter une salle
        </button>
      </div>

      {succes && (
        <Message type="succes" onFermer={() => setSucces(null)}>
          {succes}
        </Message>
      )}
      {erreur && <Message type="erreur">{erreur}</Message>}

      {salles === null ? (
        <Chargement />
      ) : (
        <div className="cadre-tableau">
          <table className="tableau">
            <caption className="visuellement-cache">Salles et état d'ouverture</caption>
            <thead>
              <tr>
                <th scope="col">Salle</th>
                <th scope="col">Bâtiment</th>
                <th scope="col">Capacité</th>
                <th scope="col">Horaires</th>
                <th scope="col">État</th>
                <th scope="col">Réservations à venir</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {salles.map((salle) => (
                <tr key={salle.id} className={salle.etat === "retiree" ? "ligne--retiree" : undefined}>
                  <th scope="row">
                    <span className="code-salle">{salle.code}</span>
                    {salle.nom && <small className="discret"> {salle.nom}</small>}
                  </th>
                  <td>
                    {salle.batiment.code}, niveau {salle.etage}
                  </td>
                  <td>{salle.capacite}</td>
                  <td className="heure">
                    {formatHeure(salle.heureOuverture)} – {formatHeure(salle.heureFermeture)}
                  </td>
                  <td>
                    <span className={`etat etat--${salle.etat}`}>{LIBELLES_ETATS[salle.etat]}</span>
                  </td>
                  <td>{salle.reservationsAVenir ?? "—"}</td>
                  <td>
                    <div className="rangee-boutons">
                      <button
                        type="button"
                        className="bouton bouton--sobre bouton--petit"
                        onClick={() => setEdition(salle)}
                      >
                        Modifier
                      </button>
                      <ChangementEtat salle={salle} envoi={envoi} onChanger={(etat) => void changerEtat(salle, etat)} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {edition && (
        <PanneauLateral
          titre={edition === "nouvelle" ? "Nouvelle salle" : `Modifier ${edition.code}`}
          onFermer={() => {
            setEdition(null);
            setErreurFormulaire(null);
          }}
        >
          {erreurFormulaire && <Message type="erreur">{erreurFormulaire}</Message>}
          <FormulaireSalle
            salle={edition === "nouvelle" ? null : edition}
            batiments={batiments}
            envoi={envoi}
            onValider={(donnees) => void enregistrer(donnees)}
          />
        </PanneauLateral>
      )}
    </div>
  );
}
