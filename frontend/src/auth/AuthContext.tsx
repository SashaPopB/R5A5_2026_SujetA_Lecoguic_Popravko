/**
 * État d'authentification partagé (service d'authentification du cours).
 * Le jeton lui-même est dans un cookie httpOnly : le frontend ne connaît que
 * le compte connecté, demandé à l'API au démarrage.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { messageErreur, quandSessionExpiree } from "../api/client.ts";
import type { Utilisateur } from "../models/index.ts";
import * as authService from "../services/authService.ts";
import type { Inscription } from "../services/authService.ts";

interface ContexteAuth {
  utilisateur: Utilisateur | null;
  chargement: boolean;
  erreurDemarrage: string | null;
  connecter: (email: string, motDePasse: string) => Promise<Utilisateur>;
  inscrire: (donnees: Inscription) => Promise<Utilisateur>;
  deconnecter: () => Promise<void>;
}

const Contexte = createContext<ContexteAuth | null>(null);

export function FournisseurAuth({ children }: { children: ReactNode }) {
  const [utilisateur, setUtilisateur] = useState<Utilisateur | null>(null);
  const [chargement, setChargement] = useState(true);
  const [erreurDemarrage, setErreurDemarrage] = useState<string | null>(null);

  useEffect(() => {
    let actif = true;
    authService
      .compteConnecte()
      .then((compte) => actif && setUtilisateur(compte))
      .catch((erreur: unknown) => actif && setErreurDemarrage(messageErreur(erreur)))
      .finally(() => actif && setChargement(false));
    // Session impossible à prolonger : retour à l'écran de connexion.
    quandSessionExpiree(() => setUtilisateur(null));
    return () => {
      actif = false;
      quandSessionExpiree(null);
    };
  }, []);

  const connecter = useCallback(async (email: string, motDePasse: string) => {
    const compte = await authService.connexion(email, motDePasse);
    setUtilisateur(compte);
    return compte;
  }, []);

  const inscrire = useCallback(async (donnees: Inscription) => {
    const compte = await authService.inscription(donnees);
    setUtilisateur(compte);
    return compte;
  }, []);

  const deconnecter = useCallback(async () => {
    try {
      await authService.deconnexion();
    } finally {
      setUtilisateur(null);
    }
  }, []);

  const valeur = useMemo(
    () => ({ utilisateur, chargement, erreurDemarrage, connecter, inscrire, deconnecter }),
    [utilisateur, chargement, erreurDemarrage, connecter, inscrire, deconnecter],
  );
  return <Contexte.Provider value={valeur}>{children}</Contexte.Provider>;
}

export function useAuth(): ContexteAuth {
  const contexte = useContext(Contexte);
  if (!contexte) throw new Error("useAuth doit être utilisé sous <FournisseurAuth>.");
  return contexte;
}

/** Compte connecté, dans un composant placé derrière <RouteProtegee>. */
export function useUtilisateur(): Utilisateur {
  const { utilisateur } = useAuth();
  if (!utilisateur) throw new Error("useUtilisateur suppose une route protégée.");
  return utilisateur;
}
