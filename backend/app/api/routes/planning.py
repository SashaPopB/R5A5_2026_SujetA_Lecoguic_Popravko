"""Planning d'une journée (A-01)."""
from flask import Blueprint

from ...composition import services
from .. import dto, mappers
from ..openapi import documenter
from ..securite import acteur_courant
from ..validation import lire_parametres, repondre

bp = Blueprint("planning", __name__, url_prefix="/api")


@bp.get("/planning")
@documenter("Occupation des salles pour un jour", tags=("Planning",),
            parametres=dto.PlanningParametres, reponses={200: dto.PlanningSortie},
            description="Salles non retirées, réservations actives et créneaux fermés du jour. "
                        "Qui a réservé et pourquoi n'est visible que du titulaire et du "
                        "gestionnaire.")
def planning():
    jour = lire_parametres(dto.PlanningParametres).date or services().horloge.maintenant().date()
    vue = services().planning.du_jour(acteur_courant(), jour)
    return repondre(mappers.planning(vue, services().parametres.fuseau))
