import { ErreurApi, requete } from "../api/client.ts";
import type { UtilisateurDto } from "../api/dto.ts";
import { versUtilisateur } from "../api/mappers.ts";
import type { Utilisateur } from "../models/index.ts";

export interface Inscription {
  email: string;
  motDePasse: string;
  nom: string;
  prenom: string;
}

export async function connexion(email: string, motDePasse: string): Promise<Utilisateur> {
  const dto = await requete<UtilisateurDto>("/auth/connexion", {
    methode: "POST",
    corps: { email, mot_de_passe: motDePasse },
  });
  return versUtilisateur(dto);
}

export async function inscription(donnees: Inscription): Promise<Utilisateur> {
  const dto = await requete<UtilisateurDto>("/auth/inscription", {
    methode: "POST",
    corps: { email: donnees.email, mot_de_passe: donnees.motDePasse, nom: donnees.nom, prenom: donnees.prenom },
  });
  return versUtilisateur(dto);
}

/** Compte connecté, ou null si aucune session valide (les autres erreurs remontent). */
export async function compteConnecte(): Promise<Utilisateur | null> {
  try {
    return versUtilisateur(await requete<UtilisateurDto>("/auth/moi"));
  } catch (erreur) {
    if (erreur instanceof ErreurApi && erreur.statut === 401) return null;
    throw erreur;
  }
}

export async function deconnexion(): Promise<void> {
  await requete<void>("/auth/deconnexion", { methode: "POST" });
}
