"""Gestion des comptes par le gestionnaire (attribution des rôles)."""
import uuid
from collections.abc import Sequence

from ..domaine.enums import Role
from ..domaine.erreurs import Conflit, RessourceIntrouvable
from .contexte import Socle, exiger_gestionnaire
from .ports import DepotUtilisateurs, Journal, Utilisateur
from .reservations import Pagination


class ServiceUtilisateurs:
    def __init__(self, socle: Socle, *, utilisateurs: DepotUtilisateurs,
                 journal_securite: Journal) -> None:
        self._socle = socle
        self._utilisateurs = utilisateurs
        self._journal_securite = journal_securite

    def rechercher(self, acteur: Utilisateur, recherche: str | None,
                   pagination: Pagination) -> tuple[Sequence[Utilisateur], int]:
        exiger_gestionnaire(acteur.role)
        return self._utilisateurs.rechercher(recherche, pagination.page, pagination.taille)

    def changer_role(self, acteur: Utilisateur, utilisateur_id: uuid.UUID,
                     role: Role) -> Utilisateur:
        exiger_gestionnaire(acteur.role)
        if utilisateur_id == acteur.id:
            # Un gestionnaire qui se retire ses droits par erreur pourrait
            # laisser l'application sans administrateur.
            raise Conflit("Vous ne pouvez pas modifier votre propre rôle.", code="propre_role")
        cible = self._utilisateurs.obtenir(utilisateur_id)
        if cible is None:
            raise RessourceIntrouvable("Utilisateur introuvable.", code="utilisateur_introuvable")
        ancien = cible.role
        cible.role = role
        self._socle.transaction.valider()
        self._journal_securite.evenement(
            "utilisateur.role_modifie", utilisateur=str(cible.id), par=str(acteur.id),
            ancien_role=str(ancien), nouveau_role=str(role))
        return cible
