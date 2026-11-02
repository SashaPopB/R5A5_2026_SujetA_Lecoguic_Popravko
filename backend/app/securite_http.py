"""Protections HTTP transverses (checklist « API Security » du cours)."""
from urllib.parse import urlsplit

from flask import Flask, Response, request
from werkzeug.exceptions import UnsupportedMediaType

from .domaine.erreurs import AccesRefuse

METHODES_AVEC_CORPS = {"POST", "PUT", "PATCH"}
METHODES_SURES = {"GET", "HEAD", "OPTIONS"}
FLUX_TEMPS_REEL = "/api/evenements"


def origine_acceptee(origine: str | None, hote: str, autorisees: frozenset[str]) -> bool:
    """Un navigateur envoie toujours Origin sur une requête venue d'un autre
    site : on refuse celles qui ne viennent ni de l'API elle-même ni d'une
    origine déclarée. Sans Origin (curl, tests, client serveur), il n'y a pas
    de navigateur à abuser : la requête passe."""
    if not origine:
        return True
    return origine in autorisees or urlsplit(origine).netloc == hote


def configurer_securite_http(app: Flask) -> None:
    hsts = app.config["HSTS_ACTIF"]
    autorisees = frozenset(app.config["ORIGINES_AUTORISEES"])

    @app.before_request
    def verifier_origine() -> None:
        """Défense en profondeur contre le CSRF, en plus de SameSite et du
        jeton anti-CSRF : écritures et flux temps réel uniquement."""
        sensible = request.method not in METHODES_SURES or request.path == FLUX_TEMPS_REEL
        if sensible and not origine_acceptee(request.headers.get("Origin"), request.host,
                                             autorisees):
            raise AccesRefuse("Origine de la requête non autorisée.", code="origine_refusee")

    @app.before_request
    def verifier_type_de_contenu() -> None:
        """Un corps doit être du JSON. Cela bloque aussi les formulaires HTML
        envoyés depuis un autre site (une des défenses contre le CSRF)."""
        if (request.method in METHODES_AVEC_CORPS and request.content_length
                and request.mimetype != "application/json"):
            raise UnsupportedMediaType()

    @app.after_request
    def entetes_de_securite(reponse: Response) -> Response:
        entetes = reponse.headers
        entetes.setdefault("X-Content-Type-Options", "nosniff")
        entetes.setdefault("X-Frame-Options", "DENY")
        entetes.setdefault("Referrer-Policy", "no-referrer")
        # Une API JSON ne charge rien : tout est interdit par défaut. La page
        # Swagger UI définit sa propre politique, moins stricte.
        entetes.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if request.path.startswith("/api/") and "Cache-Control" not in entetes:
            entetes["Cache-Control"] = "no-store"  # données personnelles : pas de cache
        if hsts:
            entetes.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return reponse
