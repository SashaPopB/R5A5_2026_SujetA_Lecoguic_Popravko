/**
 * Markdown restreint des descriptions de réservation (A-02).
 *
 * Le texte est découpé en un arbre (blocs et éléments en ligne) que React
 * affiche avec ses propres balises : aucun HTML saisi n'est jamais injecté
 * dans la page, donc pas de XSS possible par ce champ. Seuls les liens
 * http(s) et mailto deviennent cliquables (même règle que le serveur).
 *
 * Syntaxe prise en charge : **gras**, *italique* ou _italique_,
 * listes « - » / « * » et « 1. », liens [texte](url) et URL nues.
 */

export type Inline =
  | { type: "texte"; valeur: string }
  | { type: "gras"; enfants: Inline[] }
  | { type: "italique"; enfants: Inline[] }
  | { type: "lien"; url: string; enfants: Inline[] };

export type Bloc =
  | { type: "paragraphe"; lignes: Inline[][] }
  | { type: "liste"; ordonnee: boolean; elements: Inline[][] };

const PROTOCOLES_AUTORISES = new Set(["http:", "https:", "mailto:"]);

export function urlAutorisee(url: string): boolean {
  try {
    const analyse = new URL(url.trim());
    if (!PROTOCOLES_AUTORISES.has(analyse.protocol)) return false;
    return analyse.protocol === "mailto:" ? analyse.pathname.length > 0 : analyse.hostname.length > 0;
  } catch {
    return false;
  }
}

const PUCE = /^\s*[-*]\s+(.*)$/;
const NUMERO = /^\s*\d+[.)]\s+(.*)$/;

/*
 * Un seul motif, essayé de gauche à droite ; la première alternative qui
 * correspond l'emporte :
 *   1-2  [texte](url)
 *   3    **gras**
 *   4    *italique*
 *   5    _italique_ (pas au milieu d'un mot : snake_case reste intact)
 *   6    URL nue, sans la ponctuation finale (« voir https://x.fr. »)
 */
const MOTIF_EN_LIGNE =
  /\[([^\]\n]+)\]\(([^)\s]+)\)|\*\*(.+?)\*\*|\*([^*\n]+?)\*|(?<![\p{L}\p{N}])_([^_\n]+?)_(?![\p{L}\p{N}])|(https?:\/\/[^\s<>()]*[^\s<>().,;:!?'"])/u;

function analyserLigne(texte: string): Inline[] {
  const resultat: Inline[] = [];
  let reste = texte;
  while (reste.length > 0) {
    const trouve = MOTIF_EN_LIGNE.exec(reste);
    if (!trouve) {
      resultat.push({ type: "texte", valeur: reste });
      break;
    }
    if (trouve.index > 0) resultat.push({ type: "texte", valeur: reste.slice(0, trouve.index) });
    const [complet, texteLien, urlLien, gras, italique, italiqueSouligne, urlNue] = trouve;

    if (texteLien !== undefined && urlLien !== undefined) {
      resultat.push(
        urlAutorisee(urlLien)
          ? { type: "lien", url: urlLien, enfants: analyserLigne(texteLien) }
          : { type: "texte", valeur: complet },
      );
    } else if (gras !== undefined) {
      resultat.push({ type: "gras", enfants: analyserLigne(gras) });
    } else if (italique !== undefined || italiqueSouligne !== undefined) {
      resultat.push({ type: "italique", enfants: analyserLigne(italique ?? italiqueSouligne ?? "") });
    } else if (urlNue !== undefined) {
      resultat.push(
        urlAutorisee(urlNue)
          ? { type: "lien", url: urlNue, enfants: [{ type: "texte", valeur: urlNue }] }
          : { type: "texte", valeur: urlNue },
      );
    }
    reste = reste.slice(trouve.index + complet.length);
  }
  return fusionnerTextes(resultat);
}

function fusionnerTextes(elements: Inline[]): Inline[] {
  const fusion: Inline[] = [];
  for (const element of elements) {
    const precedent = fusion[fusion.length - 1];
    if (element.type === "texte" && precedent?.type === "texte") {
      fusion[fusion.length - 1] = { type: "texte", valeur: precedent.valeur + element.valeur };
    } else {
      fusion.push(element);
    }
  }
  return fusion;
}

export function analyserMarkdown(texte: string): Bloc[] {
  const blocs: Bloc[] = [];
  let paragraphe: string[] = [];
  let liste: { ordonnee: boolean; elements: string[] } | null = null;

  const fermerParagraphe = () => {
    if (paragraphe.length > 0) blocs.push({ type: "paragraphe", lignes: paragraphe.map(analyserLigne) });
    paragraphe = [];
  };
  const fermerListe = () => {
    if (liste) {
      blocs.push({ type: "liste", ordonnee: liste.ordonnee, elements: liste.elements.map(analyserLigne) });
    }
    liste = null;
  };

  for (const ligne of texte.replace(/\r\n?/g, "\n").split("\n")) {
    const puce = PUCE.exec(ligne);
    const numero = puce ? null : NUMERO.exec(ligne);
    if (puce || numero) {
      const ordonnee = numero !== null;
      fermerParagraphe();
      if (liste && liste.ordonnee !== ordonnee) fermerListe();
      liste ??= { ordonnee, elements: [] };
      liste.elements.push((puce ?? numero)?.[1] ?? "");
    } else if (ligne.trim() === "") {
      fermerParagraphe();
      fermerListe();
    } else {
      fermerListe();
      paragraphe.push(ligne);
    }
  }
  fermerParagraphe();
  fermerListe();
  return blocs;
}

function texteDe(elements: Inline[]): string {
  return elements.map((e) => (e.type === "texte" ? e.valeur : texteDe(e.enfants))).join("");
}

/** Version texte brut, pour les cases du planning (aperçu sur une ligne). */
export function texteBrut(texte: string): string {
  return analyserMarkdown(texte)
    .flatMap((bloc) => (bloc.type === "paragraphe" ? bloc.lignes : bloc.elements))
    .map(texteDe)
    .join(" · ");
}
