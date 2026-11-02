"""Fermeture et réouverture de créneaux par le gestionnaire (A-07)."""
import uuid
from http import HTTPStatus

from flask import Blueprint, Response

from ...composition import services
from ...domaine.enums import Role
from ...services.fermetures import DemandeFermeture
from .. import dto, mappers
from ..openapi import documenter
from ..securite import acteur_courant, roles_requis
from ..validation import lire_corps, repondre

bp = Blueprint("fermetures", __name__, url_prefix="/api/fermetures")
TAGS = ("Créneaux fermés",)


@bp.post("")
@documenter("Fermer un créneau", tags=TAGS, corps=dto.FermetureEntree,
            reponses={201: dto.FermetureCreeeSortie},
            erreurs=(HTTPStatus.NOT_FOUND, HTTPStatus.CONFLICT),
            description="Heures pleines, éventuellement sur plusieurs jours. Les réservations "
                        "actives de la plage sont annulées avec le motif de fermeture.")
@roles_requis(Role.GESTIONNAIRE)
def fermer():
    entree = lire_corps(dto.FermetureEntree)
    fermeture, annulees = services().fermetures.fermer(
        acteur_courant(),
        DemandeFermeture(entree.salle_id, entree.debut, entree.fin, entree.motif),
    )
    sortie = mappers.fermeture(fermeture, services().parametres.fuseau)
    return repondre(dto.FermetureCreeeSortie(**sortie.model_dump(),
                                             reservations_annulees=annulees),
                    HTTPStatus.CREATED)


@bp.delete("/<uuid:fermeture_id>")
@documenter("Rouvrir un créneau", tags=TAGS, reponses={204: None},
            erreurs=(HTTPStatus.NOT_FOUND,))
@roles_requis(Role.GESTIONNAIRE)
def rouvrir(fermeture_id: uuid.UUID):
    services().fermetures.rouvrir(acteur_courant(), fermeture_id)
    return Response(status=HTTPStatus.NO_CONTENT)
