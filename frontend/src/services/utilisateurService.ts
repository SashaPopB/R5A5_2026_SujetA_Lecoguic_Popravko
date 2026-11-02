import { requete } from "../api/client.ts";
import type { PageDto, UtilisateurDto } from "../api/dto.ts";
import { versPage, versUtilisateur } from "../api/mappers.ts";
import type { Page, Role, Utilisateur } from "../models/index.ts";

export async function rechercherUtilisateurs(
  recherche: string,
  page: number,
  signal?: AbortSignal,
): Promise<Page<Utilisateur>> {
  const parametres = new URLSearchParams({ page: String(page) });
  if (recherche.trim()) parametres.set("recherche", recherche.trim());
  const dto = await requete<PageDto<UtilisateurDto>>(`/utilisateurs?${parametres}`, { signal });
  return versPage(dto, versUtilisateur);
}

export async function changerRole(utilisateurId: string, role: Role): Promise<Utilisateur> {
  const dto = await requete<UtilisateurDto>(`/utilisateurs/${encodeURIComponent(utilisateurId)}`, {
    methode: "PATCH",
    corps: { role },
  });
  return versUtilisateur(dto);
}
