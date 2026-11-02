"""Traduction des erreurs en réponses JSON homogènes :
{"code": "...", "message": "...", "details": ...}."""
import logging
import sys
from http import HTTPStatus

from flask import Flask, Response, g, jsonify
from werkzeug.exceptions import HTTPException

from ..domaine.erreurs import (
    AccesRefuse,
    AuthentificationRequise,
    Conflit,
    DonneesInvalides,
    ErreurDomaine,
    RessourceIntrouvable,
    TropDeTentatives,
)
from ..extensions import db

journal_erreurs = logging.getLogger("sae.erreurs")

STATUTS_METIER: dict[type[ErreurDomaine], HTTPStatus] = {
    DonneesInvalides: HTTPStatus.BAD_REQUEST,
    AuthentificationRequise: HTTPStatus.UNAUTHORIZED,
    AccesRefuse: HTTPStatus.FORBIDDEN,
    RessourceIntrouvable: HTTPStatus.NOT_FOUND,
    Conflit: HTTPStatus.CONFLICT,
    TropDeTentatives: HTTPStatus.TOO_MANY_REQUESTS,
}

MESSAGES_HTTP = {
    HTTPStatus.NOT_FOUND: ("route_introuvable", "Cette adresse n'existe pas dans l'API."),
    HTTPStatus.METHOD_NOT_ALLOWED: ("methode_non_autorisee",
                                    "Méthode HTTP non autorisée sur cette adresse."),
    HTTPStatus.UNSUPPORTED_MEDIA_TYPE: ("type_contenu_non_supporte",
                                        "Le corps doit être envoyé en application/json."),
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: ("requete_trop_volumineuse",
                                          "Corps de requête trop volumineux."),
    HTTPStatus.BAD_REQUEST: ("requete_invalide", "Requête mal formée."),
}


def _statut_metier(erreur: ErreurDomaine) -> HTTPStatus:
    for classe in type(erreur).__mro__:
        if classe in STATUTS_METIER:
            return STATUTS_METIER[classe]
    return HTTPStatus.BAD_REQUEST


def enregistrer_gestionnaires_erreurs(app: Flask) -> None:
    @app.errorhandler(ErreurDomaine)
    def erreur_metier(erreur: ErreurDomaine) -> tuple[Response, HTTPStatus]:
        db.session.rollback()
        g.erreur = (type(erreur).__name__, erreur.message)
        corps = {"code": erreur.code, "message": erreur.message}
        if erreur.details is not None:
            corps["details"] = erreur.details
        reponse = jsonify(corps)
        if isinstance(erreur, TropDeTentatives):
            reponse.headers["Retry-After"] = str(erreur.reessayer_dans)
        return reponse, _statut_metier(erreur)

    @app.errorhandler(HTTPException)
    def erreur_http(erreur: HTTPException) -> tuple[Response, int]:
        statut = erreur.code or HTTPStatus.INTERNAL_SERVER_ERROR
        code, message = MESSAGES_HTTP.get(HTTPStatus(statut),
                                          ("erreur_http", erreur.description or erreur.name))
        g.erreur = (type(erreur).__name__, message)
        reponse = jsonify({"code": code, "message": message})
        methodes_valides = getattr(erreur, "valid_methods", None)
        if methodes_valides:
            reponse.headers["Allow"] = ", ".join(sorted(methodes_valides))
        return reponse, statut

    @app.errorhandler(Exception)
    def erreur_inattendue(erreur: Exception) -> tuple[Response, HTTPStatus]:
        # Bug : on ne révèle rien au client (ni pile, ni message). La ligne de
        # la requête portera la classe et le message de l'exception ; la pile
        # d'appels part sur une ligne à part, reliée par l'identifiant de
        # requête, que le client reçoit pour la signaler.
        db.session.rollback()
        g.erreur = (type(erreur).__name__, str(erreur)[:500])
        journal_erreurs.error("exception.non_geree", exc_info=sys.exc_info(),
                              extra={"id_requete": g.get("id_requete")})
        return (jsonify({"code": "erreur_interne",
                         "message": "Erreur interne du serveur. Elle a été journalisée.",
                         "details": {"id_requete": g.get("id_requete")}}),
                HTTPStatus.INTERNAL_SERVER_ERROR)
