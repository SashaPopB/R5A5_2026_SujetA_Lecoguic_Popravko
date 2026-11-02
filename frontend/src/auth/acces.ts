/** Qui peut ouvrir quelle page (miroir, côté interface, des règles de l'API). */
import type { Role } from "../models/index.ts";

export const ROLES_QUI_RESERVENT: readonly Role[] = ["etudiant", "enseignant"];
export const ROLES_GESTION: readonly Role[] = ["gestionnaire"];

const ACCES_PAR_PREFIXE: { prefixe: string; roles: readonly Role[] }[] = [
  { prefixe: "/mes-reservations", roles: ROLES_QUI_RESERVENT },
  { prefixe: "/gestion", roles: ROLES_GESTION },
];

/** Vrai si ce rôle peut ouvrir la page `chemin` (sert après une connexion,
 * pour ne pas renvoyer quelqu'un vers une page qui lui serait refusée). */
export function pageAutorisee(chemin: string, role: Role): boolean {
  const regle = ACCES_PAR_PREFIXE.find(({ prefixe }) => chemin === prefixe || chemin.startsWith(`${prefixe}/`));
  return !regle || regle.roles.includes(role);
}
