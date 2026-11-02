import { useId } from "react";
import { NB_JOURS_PROPOSES } from "../../config.ts";
import { aujourdhui, joursOuverts, libelleJourCourt } from "../../utils/dates.ts";

interface Props {
  date: string;
  onChange: (date: string) => void;
}

/** A-01 : aujourd'hui et les jours suivants, en un clic. */
export default function SelecteurJour({ date, onChange }: Props) {
  const idAutreDate = useId();
  const jours = joursOuverts(aujourdhui(), NB_JOURS_PROPOSES);

  return (
    <div className="selecteur-jour">
      <ul className="jours" aria-label="Jours proposés">
        {jours.map((jour, index) => {
          const { nom, numero } = libelleJourCourt(jour);
          return (
            <li key={jour}>
              <button type="button" aria-pressed={jour === date} onClick={() => onChange(jour)}>
                {index === 0 && jour === aujourdhui() ? "aujourd'hui" : nom}
                <strong>{numero}</strong>
              </button>
            </li>
          );
        })}
      </ul>
      <div className="champ champ--compact">
        <label htmlFor={idAutreDate}>Autre date</label>
        <input
          id={idAutreDate}
          type="date"
          min={aujourdhui()}
          value={date}
          onChange={(evenement) => evenement.target.value && onChange(evenement.target.value)}
        />
      </div>
    </div>
  );
}
