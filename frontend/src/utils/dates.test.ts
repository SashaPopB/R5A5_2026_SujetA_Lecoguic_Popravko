import assert from "node:assert/strict";
import { test } from "node:test";
import {
  ajouterJours,
  estDateIso,
  estJourOuvert,
  heureLocaleIso,
  joursOuverts,
  libelleHeure,
  momentIut,
} from "./dates.ts";

test("momentIut donne l'heure de Paris, été comme hiver", () => {
  assert.deepEqual(momentIut(new Date("2026-11-02T09:00:00Z")), { date: "2026-11-02", heure: 10, minute: 0 });
  assert.deepEqual(momentIut(new Date("2026-07-01T22:30:00Z")), { date: "2026-07-02", heure: 0, minute: 30 });
});

test("ajouterJours traverse les mois et le changement d'heure", () => {
  assert.equal(ajouterJours("2026-10-24", 2), "2026-10-26");
  assert.equal(ajouterJours("2026-12-31", 1), "2027-01-01");
  assert.equal(ajouterJours("2026-03-01", -1), "2026-02-28");
});

test("jours d'ouverture", () => {
  assert.equal(estJourOuvert("2026-11-07"), false); // samedi
  assert.deepEqual(joursOuverts("2026-11-06", 3), ["2026-11-06", "2026-11-09", "2026-11-10"]);
});

test("estDateIso refuse les dates impossibles", () => {
  assert.equal(estDateIso("2026-02-30"), false);
  assert.equal(estDateIso("demain"), false);
  assert.equal(estDateIso("2026-11-02"), true);
});

test("formats envoyés et affichés", () => {
  assert.equal(heureLocaleIso("2026-11-02", 8), "2026-11-02T08:00");
  assert.equal(libelleHeure(new Date("2026-11-02T13:00:00+01:00")), "13:00");
});
