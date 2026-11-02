"""Contrôleurs HTTP : ils valident les entrées (DTO), contrôlent
l'authentification, appellent un service et mettent en forme la réponse."""
from flask import Flask


def enregistrer_routes(app: Flask) -> None:
    from ..openapi import bp_documentation
    from . import (
        auth,
        evenements,
        fermetures,
        planning,
        reservations,
        salles,
        systeme,
        utilisateurs,
    )

    for module in (auth, salles, planning, reservations, fermetures, utilisateurs, evenements,
                   systeme):
        app.register_blueprint(module.bp)
    if app.config["DOCUMENTATION_API_ACTIVE"]:
        app.register_blueprint(bp_documentation)
