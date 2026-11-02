/**
 * Construction de la grille du planning (salles x heures) à partir des
 * données d'un jour. Fonction pure, testée sans navigateur.
 */
import type { CreneauReserve, Fermeture, Planning, Salle } from "../models/index.ts";
import { momentIut } from "./dates.ts";
import type { MomentIut } from "./dates.ts";

export type Segment =
  | { type: "libre"; heure: number; duree: number }
  | { type: "passe"; heure: number; duree: number }
  | { type: "hors_horaires"; heure: number; duree: number }
  | { type: "salle_fermee"; heure: number; duree: number }
  | { type: "reservation"; heure: number; duree: number; reservation: CreneauReserve }
  | { type: "fermeture"; heure: number; duree: number; fermeture: Fermeture };

export interface Rangee {
  salle: Salle;
  segments: Segment[];
}

export interface Grille {
  heures: number[];
  rangees: Rangee[];
}

const PLAGE_PAR_DEFAUT = { debut: 8, fin: 20 };

/** Heures [debut, fin[ couvertes le jour `date` par une plage d'instants. */
function heuresCouvertes(debut: Date, fin: Date, date: string): { debut: number; fin: number } {
  const d = momentIut(debut);
  const f = momentIut(fin);
  return {
    debut: d.date < date ? 0 : d.date > date ? 24 : d.heure,
    fin: f.date > date ? 24 : f.date < date ? 0 : f.heure + (f.minute > 0 ? 1 : 0),
  };
}

export function estHeurePassee(date: string, heure: number, maintenant: MomentIut): boolean {
  return date < maintenant.date || (date === maintenant.date && heure + 1 <= maintenant.heure);
}

type Occupation =
  | { type: "reservation"; cle: string; reservation: CreneauReserve }
  | { type: "fermeture"; cle: string; fermeture: Fermeture }
  | { type: "hors_horaires" | "passe" | "libre" | "salle_fermee"; cle: string };

function occupationsDeLaSalle(salle: Salle, planning: Planning, heures: number[], maintenant: MomentIut) {
  const parHeure = new Map<number, Occupation>();
  for (const reservation of planning.reservations.filter((r) => r.salleId === salle.id)) {
    const plage = heuresCouvertes(reservation.debut, reservation.fin, planning.date);
    for (let h = plage.debut; h < plage.fin; h++) {
      parHeure.set(h, { type: "reservation", cle: `r:${reservation.id}`, reservation });
    }
  }
  for (const fermeture of planning.fermetures.filter((f) => f.salleId === salle.id)) {
    const plage = heuresCouvertes(fermeture.debut, fermeture.fin, planning.date);
    for (let h = plage.debut; h < plage.fin; h++) {
      if (!parHeure.has(h)) parHeure.set(h, { type: "fermeture", cle: `f:${fermeture.id}`, fermeture });
    }
  }
  return heures.map((h): Occupation => {
    if (salle.etat === "fermee") return { type: "salle_fermee", cle: "salle_fermee" };
    if (h < salle.heureOuverture || h >= salle.heureFermeture) return { type: "hors_horaires", cle: "hors" };
    const occupation = parHeure.get(h);
    if (occupation) return occupation;
    if (estHeurePassee(planning.date, h, maintenant)) return { type: "passe", cle: "passe" };
    return { type: "libre", cle: `libre:${h}` };
  });
}

export function construireGrille(planning: Planning, maintenant: MomentIut): Grille {
  const ouvertes = planning.salles.filter((s) => s.etat !== "retiree");
  const debut = ouvertes.length ? Math.min(...ouvertes.map((s) => s.heureOuverture)) : PLAGE_PAR_DEFAUT.debut;
  const fin = ouvertes.length ? Math.max(...ouvertes.map((s) => s.heureFermeture)) : PLAGE_PAR_DEFAUT.fin;
  const heures = Array.from({ length: Math.max(0, fin - debut) }, (_, i) => debut + i);

  const rangees = ouvertes.map((salle): Rangee => {
    const occupations = occupationsDeLaSalle(salle, planning, heures, maintenant);
    const segments: Segment[] = [];
    occupations.forEach((occupation, index) => {
      const heure = heures[index];
      const precedent = segments[segments.length - 1];
      const precedenteOccupation = index > 0 ? occupations[index - 1] : null;
      // Heures consécutives d'un même élément : une seule case qui s'étend.
      if (precedent && precedenteOccupation?.cle === occupation.cle && occupation.type !== "libre") {
        precedent.duree += 1;
        return;
      }
      switch (occupation.type) {
        case "reservation":
          segments.push({ type: "reservation", heure, duree: 1, reservation: occupation.reservation });
          break;
        case "fermeture":
          segments.push({ type: "fermeture", heure, duree: 1, fermeture: occupation.fermeture });
          break;
        case "libre":
          segments.push({ type: "libre", heure, duree: 1 });
          break;
        default:
          segments.push({ type: occupation.type, heure, duree: 1 });
      }
    });
    return { salle, segments };
  });
  return { heures, rangees };
}

/**
 * Heures de fin possibles pour un créneau qui commence à `heure` : on
 * s'arrête au premier obstacle (réservation, fermeture, fin des horaires).
 */
export function heuresDeFinPossibles(rangee: Rangee, heure: number, dureeMax?: number): number[] {
  const fins: number[] = [];
  let finCourante = heure;
  for (const segment of rangee.segments) {
    if (segment.heure < heure) continue;
    if (segment.type !== "libre" || segment.heure !== finCourante) break;
    finCourante = segment.heure + 1;
    fins.push(finCourante);
    if (dureeMax !== undefined && finCourante - heure >= dureeMax) break;
  }
  return fins;
}

/**
 * Heures de fin possibles pour une fermeture décidée par le gestionnaire :
 * elle peut recouvrir des réservations (qui seront annulées) mais pas une
 * autre fermeture, ni dépasser les horaires de la salle.
 */
export function heuresDeFinFermeture(rangee: Rangee, heure: number): number[] {
  const fins: number[] = [];
  let finCourante = heure;
  for (const segment of rangee.segments) {
    const finSegment = segment.heure + segment.duree;
    if (finSegment <= heure) continue;
    const bloquant =
      segment.type === "fermeture" || segment.type === "hors_horaires" || segment.type === "salle_fermee";
    if (bloquant || segment.heure > finCourante) break;
    for (let h = Math.max(segment.heure, heure); h < finSegment; h++) fins.push(h + 1);
    finCourante = finSegment;
  }
  return fins;
}
