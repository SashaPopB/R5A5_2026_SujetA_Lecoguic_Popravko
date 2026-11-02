"""Salles et bâtiments (A-07 pour l'administration)."""
import uuid
from http import HTTPStatus

from flask import Blueprint

from ...composition import services
from ...domaine.enums import Role
from ...services.salles import DonneesSalle, ModificationSalle
from .. import dto, mappers
from ..openapi import documenter
from ..securite import acteur_courant, roles_requis
from ..validation import lire_corps, lire_parametres, repondre

bp = Blueprint("salles", __name__, url_prefix="/api")
TAGS = ("Salles",)


@bp.get("/batiments")
@documenter("Lister les bâtiments", tags=TAGS, reponses={200: [dto.BatimentSortie]})
def lister_batiments():
    return repondre([mappers.batiment(b) for b in services().salles.lister_batiments()])


@bp.get("/salles")
@documenter("Lister les salles", tags=TAGS, parametres=dto.SallesParametres,
            reponses={200: [dto.SalleSortie]}, erreurs=(HTTPStatus.FORBIDDEN,),
            description="Les salles retirées n'apparaissent que pour le gestionnaire, avec "
                        "`inclure_retirees=true`.")
def lister_salles():
    parametres = lire_parametres(dto.SallesParametres)
    acteur = acteur_courant()
    service = services().salles
    salles = (service.lister_toutes(acteur) if parametres.inclure_retirees
              else service.lister_proposees())
    if acteur.role == Role.GESTIONNAIRE:
        a_venir = service.compter_reservations_a_venir(salles)
        return repondre([mappers.salle(s, a_venir.get(s.id, 0)) for s in salles])
    return repondre([mappers.salle(s) for s in salles])


@bp.post("/salles")
@documenter("Créer une salle", tags=TAGS, corps=dto.SalleCreationEntree,
            reponses={201: dto.SalleSortie}, erreurs=(HTTPStatus.CONFLICT,))
@roles_requis(Role.GESTIONNAIRE)
def creer_salle():
    entree = lire_corps(dto.SalleCreationEntree)
    salle = services().salles.creer(acteur_courant(), DonneesSalle(**entree.model_dump()))
    return repondre(mappers.salle(salle, 0), HTTPStatus.CREATED)


@bp.patch("/salles/<uuid:salle_id>")
@documenter("Modifier, ouvrir, fermer ou retirer une salle", tags=TAGS,
            corps=dto.SalleModificationEntree, reponses={200: dto.SalleModifieeSortie},
            erreurs=(HTTPStatus.NOT_FOUND,),
            description="Fermer ou retirer une salle annule ses réservations à venir ; "
                        "réduire ses horaires annule celles qui en sortent. Le nombre "
                        "d'annulations est renvoyé dans `reservations_annulees`.")
@roles_requis(Role.GESTIONNAIRE)
def modifier_salle(salle_id: uuid.UUID):
    entree = lire_corps(dto.SalleModificationEntree)
    # Seuls les champs réellement envoyés sont modifiés (PATCH partiel).
    valeurs = entree.model_dump(include=entree.model_fields_set)
    salle, annulees = services().salles.modifier(acteur_courant(), salle_id,
                                                 ModificationSalle(valeurs))
    a_venir = services().salles.compter_reservations_a_venir([salle]).get(salle.id, 0)
    return repondre(mappers.salle_modifiee(salle, a_venir, annulees))
