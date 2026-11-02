import type { EtatFlux } from "../../services/tempsReel.ts";

const LIBELLES: Record<EtatFlux, string> = {
  connecte: "Mise à jour en direct",
  connexion: "Connexion au direct…",
  deconnecte: "Direct interrompu, nouvel essai en cours",
};

/** Indique si le planning se met à jour tout seul (A-04). */
export default function EtatDirect({ etat }: { etat: EtatFlux }) {
  return (
    <p className={`etat-direct etat-direct--${etat}`} role="status" aria-live="polite">
      <span className="etat-direct__pastille" aria-hidden="true" />
      {LIBELLES[etat]}
    </p>
  );
}
