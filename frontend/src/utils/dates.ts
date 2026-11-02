/**
 * Dates « calendaires » (AAAA-MM-JJ) et heures de l'IUT.
 *
 * Les calculs de jours se font sur des dates UTC à minuit : ainsi, aucun
 * décalage horaire du poste ni changement d'heure ne fait glisser une date.
 * Les instants (Date) sont toujours affichés dans le fuseau de l'IUT.
 */
import { FUSEAU_IUT, JOURS_OUVERTURE } from "../config.ts";

const partiesIut = new Intl.DateTimeFormat("en-GB", {
  timeZone: FUSEAU_IUT,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

export interface MomentIut {
  /** Jour à l'IUT, AAAA-MM-JJ. */
  date: string;
  heure: number;
  minute: number;
}

/** Jour et heure de l'IUT correspondant à un instant. */
export function momentIut(instant: Date): MomentIut {
  const parties: Record<string, string> = {};
  for (const partie of partiesIut.formatToParts(instant)) parties[partie.type] = partie.value;
  return {
    date: `${parties.year}-${parties.month}-${parties.day}`,
    heure: Number(parties.hour),
    minute: Number(parties.minute),
  };
}

export function aujourdhui(): string {
  return momentIut(new Date()).date;
}

/** AAAA-MM-JJ valide (le 31 février est refusé). */
export function estDateIso(valeur: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(valeur)) return false;
  return versUtc(valeur).toISOString().slice(0, 10) === valeur;
}

function versUtc(dateIso: string): Date {
  const [annee, mois, jour] = dateIso.split("-").map(Number);
  return new Date(Date.UTC(annee, mois - 1, jour));
}

export function ajouterJours(dateIso: string, nombre: number): string {
  const date = versUtc(dateIso);
  date.setUTCDate(date.getUTCDate() + nombre);
  return date.toISOString().slice(0, 10);
}

export function estJourOuvert(dateIso: string): boolean {
  return JOURS_OUVERTURE.includes(versUtc(dateIso).getUTCDay());
}

/** Les `nombre` prochains jours d'ouverture, à partir de `dateIso` incluse. */
export function joursOuverts(dateIso: string, nombre: number): string[] {
  const jours: string[] = [];
  for (let jour = dateIso; jours.length < nombre; jour = ajouterJours(jour, 1)) {
    if (estJourOuvert(jour)) jours.push(jour);
  }
  return jours;
}

export function premierJourOuvert(dateIso: string): string {
  return joursOuverts(dateIso, 1)[0];
}

const jourLong = new Intl.DateTimeFormat("fr-FR", {
  timeZone: "UTC",
  weekday: "long",
  day: "numeric",
  month: "long",
});
const jourCourt = new Intl.DateTimeFormat("fr-FR", { timeZone: "UTC", weekday: "short" });

/** « lundi 2 novembre » */
export function libelleJour(dateIso: string): string {
  return jourLong.format(versUtc(dateIso));
}

/** { nom: « lun. », numero: « 2 » } pour les onglets de jours. */
export function libelleJourCourt(dateIso: string): { nom: string; numero: string } {
  const date = versUtc(dateIso);
  return { nom: jourCourt.format(date), numero: String(date.getUTCDate()) };
}

const heureIut = new Intl.DateTimeFormat("fr-FR", {
  timeZone: FUSEAU_IUT,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});
const dateHeureIut = new Intl.DateTimeFormat("fr-FR", {
  timeZone: FUSEAU_IUT,
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

/** « 14:00 » à l'heure de l'IUT. */
export function libelleHeure(instant: Date): string {
  return heureIut.format(instant);
}

/** « 2 nov. 2026, 14:00 » à l'heure de l'IUT. */
export function libelleDateHeure(instant: Date): string {
  return dateHeureIut.format(instant);
}

/** 8 -> « 08:00 » */
export function formatHeure(heure: number): string {
  return `${String(heure).padStart(2, "0")}:00`;
}

/** Heure locale de l'IUT au format attendu par l'API (sans fuseau). */
export function heureLocaleIso(dateIso: string, heure: number): string {
  return `${dateIso}T${formatHeure(heure)}`;
}
