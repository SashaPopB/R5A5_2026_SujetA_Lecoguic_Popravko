import { BASE_API } from "../config.ts";
import { requete } from "../api/client.ts";
import type { PageDto, ReservationDto, ReservationEntreeDto } from "../api/dto.ts";
import { versPage, versReservation } from "../api/mappers.ts";
import type { Page, Reservation, StatutReservation } from "../models/index.ts";
import { heureLocaleIso } from "../utils/dates.ts";

export interface DemandeReservation {
  salleId: string;
  date: string;
  heureDebut: number;
  heureFin: number;
  description: string;
}

export interface FiltresHistorique {
  salleId?: string;
  du?: string;
  au?: string;
  statut?: StatutReservation;
  recherche?: string;
  page?: number;
}

function parametres(valeurs: Record<string, string | number | undefined>): string {
  const recherche = new URLSearchParams();
  for (const [cle, valeur] of Object.entries(valeurs)) {
    if (valeur !== undefined && valeur !== "") recherche.set(cle, String(valeur));
  }
  const texte = recherche.toString();
  return texte ? `?${texte}` : "";
}

export async function reserver(demande: DemandeReservation): Promise<Reservation> {
  const corps: ReservationEntreeDto = {
    salle_id: demande.salleId,
    debut: heureLocaleIso(demande.date, demande.heureDebut),
    fin: heureLocaleIso(demande.date, demande.heureFin),
    description: demande.description,
  };
  return versReservation(await requete<ReservationDto>("/reservations", { methode: "POST", corps }));
}

export async function annuler(reservationId: string, motif?: string): Promise<Reservation> {
  const corps = motif ? { statut: "annulee", motif } : { statut: "annulee" };
  return versReservation(
    await requete<ReservationDto>(`/reservations/${encodeURIComponent(reservationId)}`, { methode: "PATCH", corps }),
  );
}

/** Mes réservations, page par page (le serveur pagine toujours, 20 par défaut). */
export async function mesReservations(
  periode: "a_venir" | "passees",
  page: number,
  signal?: AbortSignal,
): Promise<Page<Reservation>> {
  const dto = await requete<PageDto<ReservationDto>>(`/moi/reservations${parametres({ periode, page })}`, {
    signal,
  });
  return versPage(dto, versReservation);
}

export async function rechercher(filtres: FiltresHistorique, signal?: AbortSignal): Promise<Page<Reservation>> {
  const dto = await requete<PageDto<ReservationDto>>(
    `/reservations${parametres({
      salle_id: filtres.salleId,
      du: filtres.du,
      au: filtres.au,
      statut: filtres.statut,
      recherche: filtres.recherche,
      page: filtres.page,
    })}`,
    { signal },
  );
  return versPage(dto, versReservation);
}

/** Lien de téléchargement du CSV (A-10). Le cookie de session suffit pour un GET. */
export function urlExport(du: string, au: string): string {
  return `${BASE_API}/reservations/export${parametres({ du, au })}`;
}
