/**
 * Gardes de routes (équivalent du « guard » vu en cours).
 * Ils améliorent l'expérience mais ne protègent rien à eux seuls : c'est
 * l'API qui refuse les actions (401 / 403).
 */
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import type { Role } from "../models/index.ts";
import Chargement from "../components/commun/Chargement.tsx";
import AccesRefusePage from "../pages/AccesRefusePage.tsx";
import { useAuth } from "./AuthContext.tsx";

export function RouteProtegee({ roles, children }: { roles?: readonly Role[]; children: ReactNode }) {
  const { utilisateur, chargement } = useAuth();
  const emplacement = useLocation();

  if (chargement) return <Chargement />;
  if (!utilisateur) return <Navigate to="/connexion" replace state={{ depuis: emplacement }} />;
  if (roles && !roles.includes(utilisateur.role)) return <AccesRefusePage />;
  return <>{children}</>;
}

/** Page de connexion : inutile (et redirigée) quand on est déjà connecté. */
export function RouteInvite({ children }: { children: ReactNode }) {
  const { utilisateur, chargement } = useAuth();
  if (chargement) return <Chargement />;
  if (utilisateur) return <Navigate to="/planning" replace />;
  return <>{children}</>;
}

/** Affichage conditionnel par rôle (équivalent de la « directive » du cours). */
export function Autorise({ roles, children }: { roles: readonly Role[]; children: ReactNode }) {
  const { utilisateur } = useAuth();
  return utilisateur && roles.includes(utilisateur.role) ? <>{children}</> : null;
}
