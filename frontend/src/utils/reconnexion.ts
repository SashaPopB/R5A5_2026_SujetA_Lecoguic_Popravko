/** Délai de reconnexion au flux temps réel (fonction pure, testée sans navigateur). */

const DELAI_INITIAL_MS = 1000;
const DELAI_MAX_MS = 30_000;

/**
 * Attente avant la tentative n° `tentative` (0 pour la première) : elle double
 * à chaque échec jusqu'à 30 s, et une part aléatoire évite qu'après un
 * redémarrage du serveur tous les clients reviennent à la même seconde.
 */
export function delaiAvantReconnexion(tentative: number, aleatoire: () => number = Math.random): number {
  const plafond = Math.min(DELAI_MAX_MS, DELAI_INITIAL_MS * 2 ** tentative);
  return Math.round(plafond / 2 + (aleatoire() * plafond) / 2);
}
