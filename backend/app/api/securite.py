"""Authentification (JWT en cookies) et contrôle d'accès par rôle (RBAC).

Refus par défaut : toute route de l'API exige une session valide, sauf celles
marquées explicitement @route_publique. Une route oubliée est donc fermée
(401), jamais ouverte ; tests/droits/test_authentification.py le vérifie pour
chaque route. Le rôle est contrôlé sur la route (@roles_requis), la
propriété de la ressource dans le cas d'usage.

Le rôle est relu en base à chaque requête (et non pris dans le jeton) :
un changement de rôle s'applique tout de suite, sans attendre l'expiration.
"""
import uuid
from collections.abc import Callable
from functools import wraps
from http import HTTPStatus
from typing import Any, ParamSpec, TypeVar

from flask import Flask, current_app, g, jsonify, request
from flask_jwt_extended import current_user, get_jwt, verify_jwt_in_request

from ..composition import services
from ..domaine.enums import Role
from ..domaine.erreurs import AccesRefuse
from ..extensions import jwt
from ..services.ports import Utilisateur
from .openapi import est_publique

P = ParamSpec("P")
R = TypeVar("R")


def acteur_courant() -> Utilisateur:
    """Utilisateur authentifié de la requête (après verify_jwt_in_request)."""
    return current_user


def identifiant_session() -> uuid.UUID:
    return uuid.UUID(get_jwt()["sid"])


def exiger_authentification() -> None:
    """before_request : 401 pour toute route non publique sans session valide
    (jeton absent, expiré, révoqué ou mal signé)."""
    if request.endpoint is None or request.method == "OPTIONS":
        return  # route inexistante ou méthode refusée : Flask répond 404 / 405
    vue = current_app.view_functions.get(request.endpoint)
    if vue is None or est_publique(vue):
        return
    verify_jwt_in_request()


def roles_requis(*roles: Role) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Décorateur RBAC : 403 si le rôle ne convient pas. La session a déjà été
    vérifiée par exiger_authentification."""

    def decorateur(vue: Callable[P, R]) -> Callable[P, R]:
        @wraps(vue)
        def enveloppe(*args: P.args, **kwargs: P.kwargs) -> R:
            if acteur_courant().role not in roles:
                noms = ", ".join(str(role) for role in roles)
                raise AccesRefuse(f"Action réservée au(x) rôle(s) : {noms}.",
                                  code="role_insuffisant")
            return vue(*args, **kwargs)

        enveloppe.roles_autorises = roles  # type: ignore[attr-defined]
        return enveloppe

    return decorateur


def _reponse_401(code: str, message: str, exception: str) -> tuple[Any, HTTPStatus]:
    g.erreur = (exception, message)  # repris par le journal de la requête
    return jsonify({"code": code, "message": message}), HTTPStatus.UNAUTHORIZED


def configurer_jwt(app: Flask) -> None:
    jwt.init_app(app)
    app.before_request(exiger_authentification)

    @jwt.user_lookup_loader
    def charger_utilisateur(_entete: dict, charge: dict) -> Utilisateur | None:
        utilisateur = services().auth.utilisateur_par_id(uuid.UUID(charge["sub"]))
        if utilisateur is not None:
            g.utilisateur_id = str(utilisateur.id)
        return utilisateur

    @jwt.token_in_blocklist_loader
    def jeton_revoque(_entete: dict, charge: dict) -> bool:
        sid = charge.get("sid")
        return sid is None or not services().auth.session_active(uuid.UUID(sid))

    @jwt.unauthorized_loader
    def sans_jeton(raison: str):
        # flask-jwt-extended passe aussi par ici pour les erreurs CSRF.
        if "CSRF" in raison:
            return _reponse_401("csrf_invalide",
                                "Jeton CSRF absent ou invalide (en-tête X-CSRF-TOKEN).",
                                "CSRFError")
        return _reponse_401("authentification_requise", "Authentification requise.",
                            "NoAuthorizationError")

    @jwt.expired_token_loader
    def jeton_expire(_entete: dict, _charge: dict):
        return _reponse_401("jeton_expire", "Session expirée, reconnectez-vous.",
                            "ExpiredSignatureError")

    @jwt.invalid_token_loader
    def jeton_invalide(raison: str):
        return _reponse_401("jeton_invalide", "Jeton d'authentification invalide.",
                            f"InvalidTokenError: {raison}")

    @jwt.revoked_token_loader
    def jeton_revoque_reponse(_entete: dict, _charge: dict):
        return _reponse_401("session_revoquee", "Cette session a été fermée.",
                            "RevokedTokenError")

    @jwt.user_lookup_error_loader
    def utilisateur_introuvable(_entete: dict, _charge: dict):
        return _reponse_401("compte_introuvable", "Ce compte n'existe plus.", "UserLookupError")
