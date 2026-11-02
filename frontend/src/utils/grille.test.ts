import assert from "node:assert/strict";
import { test } from "node:test";
import type { Planning, Salle } from "../models/index.ts";
import { construireGrille, heuresDeFinFermeture, heuresDeFinPossibles } from "./grille.ts";

const salle = (id: string, ouverture = 8, fermeture = 12, etat: Salle["etat"] = "ouverte"): Salle => ({
  id,
  code: id.toUpperCase(),
  nom: null,
  batiment: { id: "b", code: "A", nom: "A" },
  etage: 0,
  capacite: 8,
  heureOuverture: ouverture,
  heureFermeture: fermeture,
  etat,
  reservationsAVenir: null,
});

const planning = (partiel: Partial<Planning>): Planning => ({
  date: "2026-11-02",
  jourOuvert: true,
  salles: [salle("d101")],
  reservations: [],
  fermetures: [],
  ...partiel,
});

const avantLeJour = { date: "2026-11-01", heure: 12, minute: 0 };

test("cases libres et réservation qui s'étend sur deux heures", () => {
  const grille = construireGrille(
    planning({
      reservations: [
        {
          id: "r1",
          salleId: "d101",
          debut: new Date("2026-11-02T09:00:00+01:00"),
          fin: new Date("2026-11-02T11:00:00+01:00"),
          estAMoi: true,
          titulaire: null,
          description: null,
        },
      ],
    }),
    avantLeJour,
  );
  assert.deepEqual(grille.heures, [8, 9, 10, 11]);
  assert.deepEqual(
    grille.rangees[0].segments.map((s) => [s.type, s.heure, s.duree]),
    [
      ["libre", 8, 1],
      ["reservation", 9, 2],
      ["libre", 11, 1],
    ],
  );
});

test("heures passées, horaires de salle et salle fermée", () => {
  const grille = construireGrille(planning({ salles: [salle("d101", 9, 12), salle("d102", 8, 12, "fermee")] }), {
    date: "2026-11-02",
    heure: 10,
    minute: 30,
  });
  assert.deepEqual(
    grille.rangees[0].segments.map((s) => [s.type, s.heure, s.duree]),
    [
      ["hors_horaires", 8, 1],
      ["passe", 9, 1],
      ["libre", 10, 1],
      ["libre", 11, 1],
    ],
  );
  assert.deepEqual(
    grille.rangees[1].segments.map((s) => [s.type, s.duree]),
    [["salle_fermee", 4]],
  );
});

test("fermeture sur plusieurs jours rognée au jour affiché", () => {
  const grille = construireGrille(
    planning({
      fermetures: [
        {
          id: "f1",
          salleId: "d101",
          debut: new Date("2026-10-30T08:00:00+01:00"),
          fin: new Date("2026-11-03T12:00:00+01:00"),
          motif: "Travaux",
        },
      ],
    }),
    avantLeJour,
  );
  assert.deepEqual(
    grille.rangees[0].segments.map((s) => [s.type, s.heure, s.duree]),
    [["fermeture", 8, 4]],
  );
});

test("heures de fin proposées", () => {
  const grille = construireGrille(
    planning({
      reservations: [
        {
          id: "r1",
          salleId: "d101",
          debut: new Date("2026-11-02T11:00:00+01:00"),
          fin: new Date("2026-11-02T12:00:00+01:00"),
          estAMoi: false,
          titulaire: null,
          description: null,
        },
      ],
    }),
    avantLeJour,
  );
  const rangee = grille.rangees[0];
  assert.deepEqual(heuresDeFinPossibles(rangee, 8), [9, 10, 11]);
  assert.deepEqual(heuresDeFinPossibles(rangee, 8, 2), [9, 10]);
  assert.deepEqual(heuresDeFinFermeture(rangee, 9), [10, 11, 12]);
});
