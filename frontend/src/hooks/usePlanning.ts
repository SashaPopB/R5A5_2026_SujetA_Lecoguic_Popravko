/**
 * Planning d'un jour, tenu à jour en temps réel (A-04).
 *
 * Un événement du flux ne contient pas les données (seulement la salle et
 * les jours touchés) : on recharge le planning par l'API, qui applique les
 * règles de visibilité. Un numéro de requête écarte les réponses arrivées
 * dans le désordre, pour ne jamais afficher un état plus ancien.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { estAnnulation, messageErreur } from "../api/client.ts";
import type { EvenementPlanning, Planning } from "../models/index.ts";
import { chargerPlanning } from "../services/planningService.ts";
import { suivrePlanning } from "../services/tempsReel.ts";
import type { EtatFlux } from "../services/tempsReel.ts";

export interface EtatPlanning {
  planning: Planning | null;
  chargement: boolean;
  erreur: string | null;
  etatDirect: EtatFlux;
  recharger: () => void;
}

export function usePlanning(date: string): EtatPlanning {
  const [planning, setPlanning] = useState<Planning | null>(null);
  const [chargement, setChargement] = useState(true);
  const [erreur, setErreur] = useState<string | null>(null);
  const [etatDirect, setEtatDirect] = useState<EtatFlux>("connexion");
  const derniereRequete = useRef(0);
  const controleur = useRef<AbortController | null>(null);

  const recharger = useCallback(() => {
    const numero = ++derniereRequete.current;
    controleur.current?.abort();
    controleur.current = new AbortController();
    setChargement(true);
    chargerPlanning(date, controleur.current.signal)
      .then((resultat) => {
        if (numero !== derniereRequete.current) return;
        setPlanning(resultat);
        setErreur(null);
      })
      .catch((cause: unknown) => {
        if (estAnnulation(cause) || numero !== derniereRequete.current) return;
        setErreur(messageErreur(cause));
      })
      .finally(() => {
        if (numero === derniereRequete.current) setChargement(false);
      });
  }, [date]);

  useEffect(() => {
    recharger();
    const enCours = controleur; // annule la requête la plus récente au démontage
    return () => enCours.current?.abort();
  }, [recharger]);

  // Le flux reste ouvert quand on change de jour : seul le filtre change.
  const surEvenement = useRef<(evenement: EvenementPlanning) => void>(() => undefined);
  useEffect(() => {
    surEvenement.current = (evenement) => {
      if (evenement.type !== "planning" || evenement.jours.includes(date)) recharger();
    };
  }, [date, recharger]);

  useEffect(() => suivrePlanning((evenement) => surEvenement.current(evenement), setEtatDirect), []);

  return { planning, chargement, erreur, etatDirect, recharger };
}
