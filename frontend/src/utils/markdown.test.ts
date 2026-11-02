import assert from "node:assert/strict";
import { describe, test } from "node:test";
import { analyserMarkdown, texteBrut, urlAutorisee } from "./markdown.ts";

describe("analyserMarkdown", () => {
  test("gras, italique et texte simple", () => {
    assert.deepEqual(analyserMarkdown("**Projet** *SAE* fin"), [
      {
        type: "paragraphe",
        lignes: [
          [
            { type: "gras", enfants: [{ type: "texte", valeur: "Projet" }] },
            { type: "texte", valeur: " " },
            { type: "italique", enfants: [{ type: "texte", valeur: "SAE" }] },
            { type: "texte", valeur: " fin" },
          ],
        ],
      },
    ]);
  });

  test("listes à puces puis numérotée", () => {
    const blocs = analyserMarkdown("- un\n- deux\n1. premier\n2. second");
    assert.equal(blocs.length, 2);
    assert.deepEqual(
      blocs.map((b) => (b.type === "liste" ? b.ordonnee : null)),
      [false, true],
    );
  });

  test("lien autorisé", () => {
    const [bloc] = analyserMarkdown("[sujet](https://moodle.example.org/42)");
    assert.equal(bloc.type, "paragraphe");
    assert.deepEqual(bloc.type === "paragraphe" && bloc.lignes[0][0], {
      type: "lien",
      url: "https://moodle.example.org/42",
      enfants: [{ type: "texte", valeur: "sujet" }],
    });
  });

  test("un lien javascript: reste du texte inerte", () => {
    const [bloc] = analyserMarkdown("[clic](javascript:alert(1))");
    assert.equal(JSON.stringify(bloc).includes('"lien"'), false);
  });

  test("le HTML saisi reste du texte", () => {
    assert.deepEqual(analyserMarkdown("<img src=x onerror=alert(1)>"), [
      { type: "paragraphe", lignes: [[{ type: "texte", valeur: "<img src=x onerror=alert(1)>" }]] },
    ]);
  });

  test("URL nue sans la ponctuation finale", () => {
    const [bloc] = analyserMarkdown("voir https://exemple.org/doc.");
    assert.deepEqual(bloc.type === "paragraphe" && bloc.lignes[0], [
      { type: "texte", valeur: "voir " },
      { type: "lien", url: "https://exemple.org/doc", enfants: [{ type: "texte", valeur: "https://exemple.org/doc" }] },
      { type: "texte", valeur: "." },
    ]);
  });

  test("snake_case n'est pas mis en italique", () => {
    assert.deepEqual(analyserMarkdown("nom_de_variable"), [
      { type: "paragraphe", lignes: [[{ type: "texte", valeur: "nom_de_variable" }]] },
    ]);
  });
});

test("urlAutorisee", () => {
  assert.equal(urlAutorisee("https://exemple.org"), true);
  assert.equal(urlAutorisee("mailto:prof@univ.fr"), true);
  assert.equal(urlAutorisee("javascript:alert(1)"), false);
  assert.equal(urlAutorisee("data:text/html,x"), false);
  assert.equal(urlAutorisee("pas une url"), false);
});

test("texteBrut", () => {
  assert.equal(texteBrut("**Projet**\n- maquettes\n- [doc](https://x.org)"), "Projet · maquettes · doc");
});
