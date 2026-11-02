"""Fabrique de l'application Flask."""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


def create_app(nom_configuration: str | None = None) -> "Flask":
    """Construit l'application. Les imports sont faits ici pour que les
    modules du domaine restent importables (et testables) seuls, sans Flask."""
    from flask import Flask
    from werkzeug.middleware.proxy_fix import ProxyFix

    from .api.erreurs import enregistrer_gestionnaires_erreurs
    from .api.routes import enregistrer_routes
    from .api.securite import configurer_jwt
    from .cli import enregistrer_commandes
    from .composition import installer_services
    from .config import choisir_configuration, verifier_configuration
    from .extensions import db, diffuseur
    from .journalisation import configurer_journalisation
    from .limitation import configurer_limitation
    from .securite_http import configurer_securite_http

    app = Flask(__name__)
    app.config.from_object(choisir_configuration(nom_configuration))
    verifier_configuration(app.config)
    proxys = app.config["NB_PROXYS_DE_CONFIANCE"]
    if proxys:
        app.wsgi_app = ProxyFix(  # type: ignore[method-assign]
            app.wsgi_app, x_for=proxys, x_proto=proxys)

    # L'ordre d'enregistrement est l'ordre d'exécution des before_request :
    # journal d'abord (tout est tracé), puis type de contenu et origine,
    # débit, et enfin authentification (refus par défaut).
    configurer_journalisation(app)
    db.init_app(app)
    configurer_securite_http(app)
    configurer_limitation(app)
    configurer_jwt(app)
    enregistrer_gestionnaires_erreurs(app)
    installer_services(app, diffuseur)
    enregistrer_routes(app)
    enregistrer_commandes(app)
    return app
