/**
 * Grille d'occupation : une ligne par salle, une colonne par heure.
 * Tableau HTML sémantique (en-têtes de ligne et de colonne) pour que les
 * lecteurs d'écran annoncent « salle, heure » sur chaque case.
 */
import type { CSSProperties } from "react";
import type { CreneauReserve, Fermeture } from "../../models/index.ts";
import { formatHeure, libelleHeure, libelleJour } from "../../utils/dates.ts";
import type { Grille, Rangee, Segment } from "../../utils/grille.ts";
import { texteBrut } from "../../utils/markdown.ts";

export type Selection =
  | { type: "libre"; rangee: Rangee; heure: number }
  | { type: "reservation"; rangee: Rangee; reservation: CreneauReserve }
  | { type: "fermeture"; rangee: Rangee; fermeture: Fermeture };

interface Props {
  grille: Grille;
  date: string;
  /** Action proposée sur une case libre (« Réserver », « Fermer »), ou null si aucune. */
  actionCaseLibre: string | null;
  onSelection: (selection: Selection) => void;
}

function resumeReservation(reservation: CreneauReserve): { titre: string; detail: string } {
  const horaire = `${libelleHeure(reservation.debut)}–${libelleHeure(reservation.fin)}`;
  if (reservation.estAMoi)
    return { titre: "Vous", detail: reservation.description ? texteBrut(reservation.description) : horaire };
  if (reservation.titulaire) {
    return { titre: `${reservation.titulaire.prenom} ${reservation.titulaire.nom}`, detail: horaire };
  }
  return { titre: "Réservé", detail: horaire };
}

function Case({
  segment,
  rangee,
  actionCaseLibre,
  onSelection,
}: {
  segment: Segment;
  rangee: Rangee;
  actionCaseLibre: string | null;
  onSelection: (selection: Selection) => void;
}) {
  const salle = rangee.salle;
  const plage = `${formatHeure(segment.heure)} à ${formatHeure(segment.heure + segment.duree)}`;

  switch (segment.type) {
    case "libre":
      return (
        <td>
          {actionCaseLibre ? (
            <button
              type="button"
              className="case case--libre"
              aria-label={`${actionCaseLibre} : ${salle.code}, ${plage}`}
              onClick={() => onSelection({ type: "libre", rangee, heure: segment.heure })}
            >
              Libre
            </button>
          ) : (
            <span className="case case--libre">Libre</span>
          )}
        </td>
      );
    case "reservation": {
      const { titre, detail } = resumeReservation(segment.reservation);
      return (
        <td colSpan={segment.duree}>
          <button
            type="button"
            className={`case ${segment.reservation.estAMoi ? "case--mien" : "case--occupe"}`}
            aria-label={`Réservé : ${salle.code}, ${plage}, ${titre}. Voir le détail`}
            onClick={() => onSelection({ type: "reservation", rangee, reservation: segment.reservation })}
          >
            <span className="case__titre">{titre}</span>
            <span className="case__detail">{detail}</span>
          </button>
        </td>
      );
    }
    case "fermeture":
      return (
        <td colSpan={segment.duree}>
          <button
            type="button"
            className="case case--fermeture"
            aria-label={`Créneau fermé : ${salle.code}, ${plage}, ${segment.fermeture.motif}`}
            onClick={() => onSelection({ type: "fermeture", rangee, fermeture: segment.fermeture })}
          >
            <span className="case__titre">Fermé</span>
            <span className="case__detail">{segment.fermeture.motif}</span>
          </button>
        </td>
      );
    case "salle_fermee":
      return (
        <td colSpan={segment.duree} className="case case--salle-fermee">
          Salle fermée par le gestionnaire
        </td>
      );
    case "hors_horaires":
      return (
        <td colSpan={segment.duree} className="case case--hors">
          <span className="visuellement-cache">Hors horaires d'ouverture</span>
        </td>
      );
    case "passe":
      return (
        <td colSpan={segment.duree} className="case case--passe">
          <span className="visuellement-cache">Créneau passé</span>
        </td>
      );
  }
}

export default function GrillePlanning({ grille, date, actionCaseLibre, onSelection }: Props) {
  return (
    <div className="cadre-grille">
      <table className="grille" style={{ "--nb-heures": grille.heures.length } as CSSProperties}>
        <caption className="visuellement-cache">Occupation des salles, {libelleJour(date)}</caption>
        <colgroup>
          <col className="grille__col-salle" />
          {grille.heures.map((heure) => (
            <col key={heure} />
          ))}
        </colgroup>
        <thead>
          <tr>
            <th scope="col" className="grille__coin">
              Salle
            </th>
            {grille.heures.map((heure) => (
              <th scope="col" key={heure} className="heure">
                {formatHeure(heure)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grille.rangees.map((rangee) => (
            <tr key={rangee.salle.id}>
              <th scope="row" className="grille__salle">
                <span className="code-salle">{rangee.salle.code}</span>
                <small>
                  {rangee.salle.capacite} pl. · bât. {rangee.salle.batiment.code}
                  {rangee.salle.nom ? ` · ${rangee.salle.nom}` : ""}
                </small>
              </th>
              {rangee.segments.map((segment) => (
                <Case
                  key={`${segment.type}-${segment.heure}`}
                  segment={segment}
                  rangee={rangee}
                  actionCaseLibre={actionCaseLibre}
                  onSelection={onSelection}
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
