/**
 * Abonnement au flux temps réel du planning (Server-Sent Events, A-04).
 *
 * EventSource envoie le cookie de session tout seul et se reconnecte seul
 * après une coupure réseau, en renvoyant le dernier identifiant reçu
 * (en-tête Last-Event-ID) : le serveur rejoue alors les événements manqués.
 * Deux cas restent à gérer ici :
 * - le serveur refuse la reconnexion (jeton d'accès expiré, 401) : le
 *   navigateur abandonne ; on prolonge la session puis on rouvre le flux
 *   nous-mêmes, en passant le dernier identifiant dans `?depuis=` ;
 * - le serveur ne peut pas rejouer ce qui a été manqué (historique dépassé,
 *   serveur redémarré) : il le signale dans le message « connecte » et on
 *   demande une resynchronisation (rechargement du planning affiché).
 */
import { rafraichirSession } from "../api/client.ts";
import type { ConnexionFluxDto, EvenementDto } from "../api/dto.ts";
import { versEvenement } from "../api/mappers.ts";
import { BASE_API } from "../config.ts";
import type { EvenementPlanning } from "../models/index.ts";
import { delaiAvantReconnexion } from "../utils/reconnexion.ts";

export type EtatFlux = "connexion" | "connecte" | "deconnecte";

export function urlDuFlux(dernierId: string | null): string {
  const base = `${BASE_API}/evenements`;
  return dernierId ? `${base}?depuis=${encodeURIComponent(dernierId)}` : base;
}

export function suivrePlanning(
  surEvenement: (evenement: EvenementPlanning) => void,
  surEtat: (etat: EtatFlux) => void,
): () => void {
  let source: EventSource | null = null;
  let arrete = false;
  let tentatives = 0;
  let dernierId: string | null = null;
  let minuterie: number | undefined;

  const ouvrir = () => {
    if (arrete) return;
    surEtat("connexion");
    source = new EventSource(urlDuFlux(dernierId));

    source.addEventListener("connecte", (message) => {
      tentatives = 0;
      surEtat("connecte");
      try {
        const { reprise } = JSON.parse((message as MessageEvent<string>).data) as ConnexionFluxDto;
        // « initiale » : le planning vient d'être chargé ; « complete » : les
        // événements manqués arrivent juste après. Sinon, on recharge.
        if (reprise === "impossible") surEvenement({ type: "resynchronisation" });
      } catch {
        surEvenement({ type: "resynchronisation" });
      }
    });

    source.addEventListener("planning", (evenement) => {
      const message = evenement as MessageEvent<string>;
      if (message.lastEventId) dernierId = message.lastEventId;
      try {
        surEvenement(versEvenement(JSON.parse(message.data) as EvenementDto));
      } catch {
        surEvenement({ type: "resynchronisation" });
      }
    });

    source.onerror = () => {
      if (source?.readyState === EventSource.CLOSED) {
        source.close();
        surEtat("deconnecte");
        planifierReouverture();
      } else {
        surEtat("connexion"); // le navigateur retente de lui-même
      }
    };
  };

  const planifierReouverture = () => {
    const delai = delaiAvantReconnexion(tentatives);
    tentatives += 1;
    minuterie = window.setTimeout(() => {
      void rafraichirSession().finally(ouvrir);
    }, delai);
  };

  ouvrir();
  return () => {
    arrete = true;
    window.clearTimeout(minuterie);
    source?.close(); // fermé au démontage : pas de flux fantôme à chaque retour sur la page
  };
}
