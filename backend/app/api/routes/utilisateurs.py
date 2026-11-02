"""Comptes utilisateurs : consultation et attribution des rôles."""
import uuid
from http import HTTPStatus

from flask import Blueprint

from ...composition import services
from ...domaine.enums import Role
from ...services.reservations import Pagination
from .. import dto, mappers
from ..openapi import documenter
from ..securite import acteur_courant, roles_requis
from ..validation import lire_corps, lire_parametres, repondre

bp = Blueprint("utilisateurs", __name__, url_prefix="/api/utilisateurs")
TAGS = ("Utilisateurs",)


@bp.get("")
@documenter("Lister les comptes", tags=TAGS, parametres=dto.UtilisateursParametres,
            reponses={200: dto.PageUtilisateursSortie})
@roles_requis(Role.GESTIONNAIRE)
def lister():
    p = lire_parametres(dto.UtilisateursParametres)
    elements, total = services().utilisateurs.rechercher(
        acteur_courant(), p.recherche, Pagination(p.page, p.taille))
    return repondre(dto.PageUtilisateursSortie(
        elements=[mappers.utilisateur(u) for u in elements],
        total=total, page=p.page, taille=p.taille,
    ))


@bp.patch("/<uuid:utilisateur_id>")
@documenter("Changer le rôle d'un compte", tags=TAGS, corps=dto.RoleEntree,
            reponses={200: dto.UtilisateurSortie},
            erreurs=(HTTPStatus.NOT_FOUND, HTTPStatus.CONFLICT),
            description="Seul moyen d'obtenir le rôle enseignant ou gestionnaire : "
                        "l'inscription crée toujours un compte étudiant.")
@roles_requis(Role.GESTIONNAIRE)
def changer_role(utilisateur_id: uuid.UUID):
    entree = lire_corps(dto.RoleEntree)
    utilisateur = services().utilisateurs.changer_role(acteur_courant(), utilisateur_id,
                                                       entree.role)
    return repondre(mappers.utilisateur(utilisateur))
