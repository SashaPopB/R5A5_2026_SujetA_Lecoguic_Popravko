import assert from "node:assert/strict";
import { test } from "node:test";
import { delaiAvantReconnexion } from "./reconnexion.ts";

test("le délai double à chaque échec, avec une part aléatoire", () => {
  assert.deepEqual(
    [0, 1, 2, 3].map((n) => delaiAvantReconnexion(n, () => 1)),
    [1000, 2000, 4000, 8000],
  );
  assert.equal(
    delaiAvantReconnexion(2, () => 0),
    2000,
  ); // au moins la moitié du plafond
});

test("le délai est plafonné à 30 secondes", () => {
  assert.equal(
    delaiAvantReconnexion(20, () => 1),
    30_000,
  );
});
