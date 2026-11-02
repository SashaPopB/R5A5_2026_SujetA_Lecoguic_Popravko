/** Réglages partagés par toute l'application (alignés sur le backend). */

/** Toutes les heures affichées sont celles de l'IUT, quel que soit le fuseau du poste. */
export const FUSEAU_IUT = "Europe/Paris";

export const BASE_API = "/api";

/** Jours d'ouverture de l'IUT, numérotés comme Date.getUTCDay() (1 = lundi). */
export const JOURS_OUVERTURE: readonly number[] = [1, 2, 3, 4, 5];

/** Nombre de jours ouverts proposés dans le sélecteur du planning (A-01). */
export const NB_JOURS_PROPOSES = 10;

/** A-09 : durée maximale d'affilée pour un étudiant (contrôlée par l'API). */
export const DUREE_MAX_ETUDIANT_HEURES = 2;

export const DESCRIPTION_LONGUEUR_MAX = 2000;
