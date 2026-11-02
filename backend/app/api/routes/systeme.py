"""Route de santé, interrogée par les sondes de supervision."""
from http import HTTPStatus

from flask import Blueprint
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ...extensions import db
from .. import dto
from ..openapi import documenter, route_publique
from ..validation import repondre

bp = Blueprint("systeme", __name__, url_prefix="/api")


@bp.get("/sante")
@documenter("État du service", tags=("Système",),
            reponses={200: dto.SanteSortie, 503: dto.SanteSortie},
            description="Vérifie que l'API répond et que la base est joignable.")
@route_publique  # interrogée par la supervision externe, sans compte
def sante():
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db.session.rollback()
        return repondre(dto.SanteSortie(statut="degrade", base_de_donnees="indisponible"),
                        HTTPStatus.SERVICE_UNAVAILABLE)
    return repondre(dto.SanteSortie(statut="ok", base_de_donnees="ok"))
