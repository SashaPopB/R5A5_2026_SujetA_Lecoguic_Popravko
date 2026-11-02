/** Conversion DTO <-> modèles. */
import type {
  BatimentDto,
  EvenementDto,
  FermetureDto,
  PageDto,
  PlanningDto,
  ReservationDto,
  ReservationPlanningDto,
  SalleDto,
  UtilisateurDto,
} from "./dto.ts";
import type {
  Batiment,
  CreneauReserve,
  EvenementPlanning,
  Fermeture,
  Page,
  Planning,
  Reservation,
  Salle,
  Utilisateur,
} from "../models/index.ts";

/** « 08:00 » -> 8 */
function heure(texte: string): number {
  return Number(texte.split(":")[0]);
}

export function versUtilisateur(dto: UtilisateurDto): Utilisateur {
  return { id: dto.id, email: dto.email, nom: dto.nom, prenom: dto.prenom, role: dto.role };
}

export function versBatiment(dto: BatimentDto): Batiment {
  return { id: dto.id, code: dto.code, nom: dto.nom };
}

export function versSalle(dto: SalleDto): Salle {
  return {
    id: dto.id,
    code: dto.code,
    nom: dto.nom,
    batiment: versBatiment(dto.batiment),
    etage: dto.etage,
    capacite: dto.capacite,
    heureOuverture: heure(dto.heure_ouverture),
    heureFermeture: heure(dto.heure_fermeture),
    etat: dto.etat,
    reservationsAVenir: dto.reservations_a_venir ?? null,
  };
}

function versCreneauReserve(dto: ReservationPlanningDto): CreneauReserve {
  return {
    id: dto.id,
    salleId: dto.salle_id,
    debut: new Date(dto.debut),
    fin: new Date(dto.fin),
    estAMoi: dto.est_a_moi,
    titulaire: dto.titulaire ? versUtilisateur(dto.titulaire) : null,
    description: dto.description,
  };
}

export function versFermeture(dto: FermetureDto): Fermeture {
  return { id: dto.id, salleId: dto.salle_id, debut: new Date(dto.debut), fin: new Date(dto.fin), motif: dto.motif };
}

export function versPlanning(dto: PlanningDto): Planning {
  return {
    date: dto.date,
    jourOuvert: dto.jour_ouvert,
    salles: dto.salles.map(versSalle),
    reservations: dto.reservations.map(versCreneauReserve),
    fermetures: dto.fermetures.map(versFermeture),
  };
}

export function versReservation(dto: ReservationDto): Reservation {
  return {
    id: dto.id,
    salle: dto.salle,
    debut: new Date(dto.debut),
    fin: new Date(dto.fin),
    description: dto.description,
    statut: dto.statut,
    titulaire: versUtilisateur(dto.titulaire),
    creeLe: new Date(dto.cree_le),
    annuleeLe: dto.annulee_le ? new Date(dto.annulee_le) : null,
    annuleePar: dto.annulee_par ? versUtilisateur(dto.annulee_par) : null,
    motifAnnulation: dto.motif_annulation,
  };
}

export function versPage<D, M>(dto: PageDto<D>, convertir: (element: D) => M): Page<M> {
  return { elements: dto.elements.map(convertir), total: dto.total, page: dto.page, taille: dto.taille };
}

export function versEvenement(dto: EvenementDto): EvenementPlanning {
  if (dto.type === "planning") return { type: "planning", salleId: dto.salle_id ?? "", jours: dto.jours ?? [] };
  return { type: dto.type };
}
