/**
 * Client HTTP unique de l'application (rôle de l'« intercepteur ») :
 * - les jetons voyagent dans des cookies httpOnly, illisibles par le code ;
 * - pour toute modification, le jeton CSRF (cookie lisible) est recopié
 *   dans l'en-tête X-CSRF-TOKEN ;
 * - sur un 401, on tente une fois de prolonger la session puis on rejoue
 *   la requête ; si c'est impossible, l'application revient à la connexion ;
 * - toute erreur devient une ErreurApi avec un message lisible.
 */
import { BASE_API } from "../config.ts";
import type { ErreurDto } from "./dto.ts";

export class ErreurApi extends Error {
  readonly statut: number;
  readonly code: string;
  readonly details: unknown;

  constructor(message: string, statut: number, code: string, details?: unknown) {
    super(message);
    this.name = "ErreurApi";
    this.statut = statut;
    this.code = code;
    this.details = details;
  }
}

type Methode = "GET" | "POST" | "PATCH" | "DELETE";

interface Options {
  methode?: Methode;
  corps?: unknown;
  signal?: AbortSignal;
}

const ROUTES_DE_SESSION = ["/auth/connexion", "/auth/inscription", "/auth/rafraichissement", "/auth/deconnexion"];
const ROUTES_JETON_RAFRAICHISSEMENT = ["/auth/rafraichissement", "/auth/deconnexion"];

let rafraichissementEnCours: Promise<boolean> | null = null;
let surSessionExpiree: (() => void) | null = null;

/** Appelé quand la session ne peut plus être prolongée. */
export function quandSessionExpiree(rappel: (() => void) | null): void {
  surSessionExpiree = rappel;
}

export function lireCookie(nom: string): string | null {
  const trouve = document.cookie.split("; ").find((cookie) => cookie.startsWith(`${nom}=`));
  return trouve ? decodeURIComponent(trouve.slice(nom.length + 1)) : null;
}

function envoyer(chemin: string, { methode = "GET", corps, signal }: Options): Promise<Response> {
  const entetes: Record<string, string> = { Accept: "application/json" };
  if (corps !== undefined) entetes["Content-Type"] = "application/json";
  if (methode !== "GET") {
    const avecRafraichissement = ROUTES_JETON_RAFRAICHISSEMENT.some((route) => chemin.startsWith(route));
    const jeton = lireCookie(avecRafraichissement ? "csrf_refresh_token" : "csrf_access_token");
    if (jeton) entetes["X-CSRF-TOKEN"] = jeton;
  }
  return fetch(BASE_API + chemin, {
    method: methode,
    headers: entetes,
    body: corps === undefined ? undefined : JSON.stringify(corps),
    credentials: "same-origin",
    signal,
  });
}

/** Prolonge la session (un seul appel à la fois, partagé par les requêtes en attente). */
export function rafraichirSession(): Promise<boolean> {
  rafraichissementEnCours ??= envoyer("/auth/rafraichissement", { methode: "POST" })
    .then((reponse) => reponse.ok)
    .catch(() => false)
    .finally(() => {
      rafraichissementEnCours = null;
    });
  return rafraichissementEnCours;
}

/** Requête abandonnée volontairement (changement de page, de jour...). */
export function estAnnulation(erreur: unknown): boolean {
  return erreur instanceof DOMException && erreur.name === "AbortError";
}

export async function requete<T>(chemin: string, options: Options = {}): Promise<T> {
  let reponse: Response;
  try {
    reponse = await envoyer(chemin, options);
    if (reponse.status === 401 && !ROUTES_DE_SESSION.some((route) => chemin.startsWith(route))) {
      if (await rafraichirSession()) reponse = await envoyer(chemin, options);
      if (reponse.status === 401) surSessionExpiree?.();
    }
  } catch (erreur) {
    if (estAnnulation(erreur)) throw erreur;
    throw new ErreurApi("Le serveur ne répond pas. Vérifiez votre connexion.", 0, "reseau");
  }

  if (reponse.status === 204) return undefined as T;
  const corps: unknown = await reponse.json().catch(() => null);
  if (!reponse.ok) {
    const erreur = (corps ?? {}) as Partial<ErreurDto>;
    throw new ErreurApi(
      erreur.message ?? "Le serveur n'a pas répondu comme prévu.",
      reponse.status,
      erreur.code ?? "inconnu",
      erreur.details,
    );
  }
  return corps as T;
}

/** Message affichable pour n'importe quelle erreur attrapée. */
export function messageErreur(erreur: unknown): string {
  if (erreur instanceof ErreurApi) return erreur.message;
  return "Une erreur inattendue est survenue.";
}
