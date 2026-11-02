import { requete } from "../api/client.ts";
import type { BatimentDto, FermetureCreeeDto, SalleDto, SalleEntreeDto, SalleModifieeDto } from "../api/dto.ts";
import { versBatiment, versFermeture, versSalle } from "../api/mappers.ts";
import type { Batiment, EtatSalle, Fermeture, Salle } from "../models/index.ts";
import { formatHeure, heureLocaleIso } from "../utils/dates.ts";

export interface DonneesSalle {
  code?: string;
  nom?: string | null;
  batimentId?: string;
  etage?: number;
  capacite?: number;
  heureOuverture?: number;
  heureFermeture?: number;
  etat?: EtatSalle;
}

function versEntree(donnees: DonneesSalle): SalleEntreeDto {
  const entree: SalleEntreeDto = {};
  if (donnees.code !== undefined) entree.code = donnees.code;
  if (donnees.nom !== undefined) entree.nom = donnees.nom;
  if (donnees.batimentId !== undefined) entree.batiment_id = donnees.batimentId;
  if (donnees.etage !== undefined) entree.etage = donnees.etage;
  if (donnees.capacite !== undefined) entree.capacite = donnees.capacite;
  if (donnees.heureOuverture !== undefined) entree.heure_ouverture = formatHeure(donnees.heureOuverture);
  if (donnees.heureFermeture !== undefined) entree.heure_fermeture = formatHeure(donnees.heureFermeture);
  if (donnees.etat !== undefined) entree.etat = donnees.etat;
  return entree;
}

export async function listerBatiments(): Promise<Batiment[]> {
  return (await requete<BatimentDto[]>("/batiments")).map(versBatiment);
}

export async function listerSalles(inclureRetirees = false, signal?: AbortSignal): Promise<Salle[]> {
  const suffixe = inclureRetirees ? "?inclure_retirees=true" : "";
  return (await requete<SalleDto[]>(`/salles${suffixe}`, { signal })).map(versSalle);
}

export async function creerSalle(donnees: DonneesSalle): Promise<Salle> {
  return versSalle(await requete<SalleDto>("/salles", { methode: "POST", corps: versEntree(donnees) }));
}

/** Modifie une salle ; renvoie aussi le nombre de réservations annulées. */
export async function modifierSalle(
  salleId: string,
  changements: DonneesSalle,
): Promise<{ salle: Salle; reservationsAnnulees: number }> {
  const dto = await requete<SalleModifieeDto>(`/salles/${encodeURIComponent(salleId)}`, {
    methode: "PATCH",
    corps: versEntree(changements),
  });
  return { salle: versSalle(dto), reservationsAnnulees: dto.reservations_annulees };
}

export interface DemandeFermeture {
  salleId: string;
  date: string;
  heureDebut: number;
  heureFin: number;
  motif: string;
}

export async function fermerCreneau(
  demande: DemandeFermeture,
): Promise<{ fermeture: Fermeture; reservationsAnnulees: number }> {
  const dto = await requete<FermetureCreeeDto>("/fermetures", {
    methode: "POST",
    corps: {
      salle_id: demande.salleId,
      debut: heureLocaleIso(demande.date, demande.heureDebut),
      fin: heureLocaleIso(demande.date, demande.heureFin),
      motif: demande.motif,
    },
  });
  return { fermeture: versFermeture(dto), reservationsAnnulees: dto.reservations_annulees };
}

export async function rouvrirCreneau(fermetureId: string): Promise<void> {
  await requete<void>(`/fermetures/${encodeURIComponent(fermetureId)}`, { methode: "DELETE" });
}
