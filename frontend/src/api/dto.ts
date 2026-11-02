/**
 * DTO : données telles que l'API les envoie (snake_case, dates en texte).
 * L'application ne les manipule jamais directement : api/mappers.ts les
 * convertit en modèles (src/models). Si le contrat de l'API change, seuls
 * ce fichier et les mappers bougent.
 */

export type RoleDto = "etudiant" | "enseignant" | "gestionnaire";
export type EtatSalleDto = "ouverte" | "fermee" | "retiree";
export type StatutReservationDto = "active" | "annulee";

export interface UtilisateurDto {
  id: string;
  email: string;
  nom: string;
  prenom: string;
  role: RoleDto;
}

export type PersonneDto = UtilisateurDto;

export interface BatimentDto {
  id: string;
  code: string;
  nom: string;
}

export interface SalleDto {
  id: string;
  code: string;
  nom: string | null;
  batiment: BatimentDto;
  etage: number;
  capacite: number;
  heure_ouverture: string;
  heure_fermeture: string;
  etat: EtatSalleDto;
  reservations_a_venir: number | null;
}

export interface SalleModifieeDto extends SalleDto {
  reservations_annulees: number;
}

export interface ReservationPlanningDto {
  id: string;
  salle_id: string;
  debut: string;
  fin: string;
  est_a_moi: boolean;
  titulaire: PersonneDto | null;
  description: string | null;
}

export interface FermetureDto {
  id: string;
  salle_id: string;
  debut: string;
  fin: string;
  motif: string;
}

export interface FermetureCreeeDto extends FermetureDto {
  reservations_annulees: number;
}

export interface PlanningDto {
  date: string;
  jour_ouvert: boolean;
  salles: SalleDto[];
  reservations: ReservationPlanningDto[];
  fermetures: FermetureDto[];
}

export interface ReservationDto {
  id: string;
  salle: { id: string; code: string; nom: string | null };
  debut: string;
  fin: string;
  description: string;
  statut: StatutReservationDto;
  titulaire: PersonneDto;
  cree_le: string;
  annulee_le: string | null;
  annulee_par: PersonneDto | null;
  motif_annulation: string | null;
}

export interface PageDto<T> {
  elements: T[];
  total: number;
  page: number;
  taille: number;
}

export interface ErreurDto {
  code: string;
  message: string;
  details?: unknown;
}

/** Corps envoyés à l'API. */
export interface ReservationEntreeDto {
  salle_id: string;
  debut: string;
  fin: string;
  description: string;
}

export interface FermetureEntreeDto {
  salle_id: string;
  debut: string;
  fin: string;
  motif: string;
}

export interface SalleEntreeDto {
  code?: string;
  nom?: string | null;
  batiment_id?: string;
  etage?: number;
  capacite?: number;
  heure_ouverture?: string;
  heure_fermeture?: string;
  etat?: EtatSalleDto;
}

/** Premier message du flux : `reprise` dit si les événements manqués suivent. */
export interface ConnexionFluxDto {
  type: "connecte";
  reprise: "initiale" | "complete" | "impossible";
}

export interface EvenementDto {
  type: "planning" | "salles" | "resynchronisation";
  salle_id?: string;
  jours?: string[];
}
