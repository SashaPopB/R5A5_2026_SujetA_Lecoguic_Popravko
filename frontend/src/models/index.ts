/** Modèles internes du frontend (indépendants de la forme des DTO). */

export type Role = "etudiant" | "enseignant" | "gestionnaire";
export type EtatSalle = "ouverte" | "fermee" | "retiree";
export type StatutReservation = "active" | "annulee";

export interface Utilisateur {
  id: string;
  email: string;
  nom: string;
  prenom: string;
  role: Role;
}

export interface Batiment {
  id: string;
  code: string;
  nom: string;
}

export interface Salle {
  id: string;
  code: string;
  nom: string | null;
  batiment: Batiment;
  etage: number;
  capacite: number;
  /** Heures pleines, ex. 8 et 20. */
  heureOuverture: number;
  heureFermeture: number;
  etat: EtatSalle;
  /** Renseigné pour le gestionnaire uniquement. */
  reservationsAVenir: number | null;
}

/** Réservation vue dans le planning : qui et pourquoi ne sont visibles que
 * du titulaire et du gestionnaire. */
export interface CreneauReserve {
  id: string;
  salleId: string;
  debut: Date;
  fin: Date;
  estAMoi: boolean;
  titulaire: Utilisateur | null;
  description: string | null;
}

export interface Fermeture {
  id: string;
  salleId: string;
  debut: Date;
  fin: Date;
  motif: string;
}

export interface Planning {
  date: string;
  jourOuvert: boolean;
  salles: Salle[];
  reservations: CreneauReserve[];
  fermetures: Fermeture[];
}

export interface Reservation {
  id: string;
  salle: { id: string; code: string; nom: string | null };
  debut: Date;
  fin: Date;
  description: string;
  statut: StatutReservation;
  titulaire: Utilisateur;
  creeLe: Date;
  annuleeLe: Date | null;
  annuleePar: Utilisateur | null;
  motifAnnulation: string | null;
}

export interface Page<T> {
  elements: T[];
  total: number;
  page: number;
  taille: number;
}

export type EvenementPlanning =
  | { type: "planning"; salleId: string; jours: string[] }
  | { type: "salles" }
  | { type: "resynchronisation" };

export const LIBELLES_ROLES: Record<Role, string> = {
  etudiant: "Étudiant",
  enseignant: "Enseignant",
  gestionnaire: "Gestionnaire",
};

export const LIBELLES_ETATS: Record<EtatSalle, string> = {
  ouverte: "Ouverte",
  fermee: "Fermée",
  retiree: "Retirée",
};

export const LIBELLES_STATUTS: Record<StatutReservation, string> = {
  active: "Active",
  annulee: "Annulée",
};

export function peutReserver(role: Role): boolean {
  return role === "etudiant" || role === "enseignant";
}
