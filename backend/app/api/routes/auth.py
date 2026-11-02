"""Routes d'authentification : les jetons voyagent dans des cookies httpOnly."""
from http import HTTPStatus

from flask import Blueprint, Response
from flask_jwt_extended import (
    create_access_token,
    create_refresh_token,
    get_jwt,
    get_jwt_identity,
    set_access_cookies,
    set_refresh_cookies,
    unset_jwt_cookies,
    verify_jwt_in_request,
)
from flask_jwt_extended.exceptions import JWTExtendedException
from jwt.exceptions import PyJWTError

from ...composition import services
from ...services.ports import Utilisateur
from .. import dto, mappers
from ..openapi import documenter, route_publique
from ..securite import acteur_courant, identifiant_session
from ..validation import lire_corps, repondre

bp = Blueprint("auth", __name__, url_prefix="/api/auth")
TAGS = ("Authentification",)


def _ouvrir_session(utilisateur: Utilisateur, statut: HTTPStatus) -> tuple[Response, HTTPStatus]:
    session = services().auth.ouvrir_session(utilisateur)
    # Charge utile minimale : identifiant du compte et de la session, rien
    # de sensible (un JWT se décode sans clé).
    revendications = {"sid": str(session.id)}
    reponse, statut = repondre(mappers.utilisateur(utilisateur), statut)
    set_access_cookies(reponse, create_access_token(str(utilisateur.id),
                                                    additional_claims=revendications))
    set_refresh_cookies(reponse, create_refresh_token(str(utilisateur.id),
                                                      additional_claims=revendications))
    return reponse, statut


@bp.post("/inscription")
@documenter("Créer un compte étudiant", tags=TAGS, corps=dto.InscriptionEntree,
            reponses={201: dto.UtilisateurSortie},
            erreurs=(HTTPStatus.CONFLICT, HTTPStatus.TOO_MANY_REQUESTS),
            description="Le rôle est toujours « etudiant ». Ouvre directement une session. "
                        "400 `mot_de_passe_previsible` pour un mot de passe trop courant, "
                        "une suite (123456789012) ou qui reprend le nom ou l'adresse.")
@route_publique  # il faut pouvoir créer un compte sans en avoir
def inscription():
    entree = lire_corps(dto.InscriptionEntree)
    utilisateur = services().auth.inscrire(entree.email, entree.mot_de_passe,
                                           entree.nom, entree.prenom)
    return _ouvrir_session(utilisateur, HTTPStatus.CREATED)


@bp.post("/connexion")
@documenter("Se connecter", tags=TAGS, corps=dto.ConnexionEntree,
            reponses={200: dto.UtilisateurSortie},
            erreurs=(HTTPStatus.UNAUTHORIZED, HTTPStatus.TOO_MANY_REQUESTS),
            description="Même réponse 401 pour une adresse inconnue et un mot de passe faux. "
                        "Après 3 échecs consécutifs sur une adresse, chaque nouvel essai doit "
                        "attendre un délai qui double (1 s, 2 s, 4 s… jusqu'à 15 min) : 429 avec "
                        "l'en-tête Retry-After. Limite supplémentaire par adresse IP.")
@route_publique  # point d'entrée de la session
def connexion():
    entree = lire_corps(dto.ConnexionEntree)
    utilisateur = services().auth.authentifier(entree.email, entree.mot_de_passe)
    return _ouvrir_session(utilisateur, HTTPStatus.OK)


@bp.post("/rafraichissement")
@documenter("Prolonger la session", tags=TAGS, reponses={204: None},
            description="Utilise `refresh_token_cookie` et l'en-tête X-CSRF-TOKEN recopié "
                        "du cookie `csrf_refresh_token`. Dépose un nouveau jeton d'accès.")
@route_publique  # le jeton d'accès est expiré : on vérifie le jeton de rafraîchissement
def rafraichissement():
    verify_jwt_in_request(refresh=True)
    jeton = create_access_token(get_jwt_identity(), additional_claims={"sid": get_jwt()["sid"]})
    reponse = Response(status=HTTPStatus.NO_CONTENT)
    set_access_cookies(reponse, jeton)
    return reponse


@bp.post("/deconnexion")
@documenter("Se déconnecter", tags=TAGS, reponses={204: None},
            description="Révoque la session côté serveur (les deux jetons deviennent "
                        "inutilisables) et efface les cookies.")
@route_publique  # doit effacer les cookies même si la session a déjà expiré
def deconnexion():
    try:
        verify_jwt_in_request(refresh=True)
        services().auth.revoquer_session(identifiant_session())
    except (JWTExtendedException, PyJWTError):
        # Session déjà expirée ou absente : il reste à effacer les cookies.
        pass
    reponse = Response(status=HTTPStatus.NO_CONTENT)
    unset_jwt_cookies(reponse)
    return reponse


@bp.get("/moi")
@documenter("Compte connecté", tags=TAGS, reponses={200: dto.UtilisateurSortie})
def moi():
    return repondre(mappers.utilisateur(acteur_courant()))
