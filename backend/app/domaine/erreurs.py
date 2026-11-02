"""Erreurs métier.

Les services lèvent ces exceptions ; ils ne connaissent pas les codes HTTP.
La traduction en réponse HTTP est faite par la couche API (api/erreurs.py).
"""
from typing import Any


class ErreurDomaine(Exception):
    """Erreur fonctionnelle, présentable telle quelle à l'utilisateur."""

    code = "erreur_metier"

    def __init__(self, message: str, *, code: str | None = None,
                 details: Any = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.details = details


class DonneesInvalides(ErreurDomaine):
    code = "donnees_invalides"


class AuthentificationRequise(ErreurDomaine):
    code = "authentification_requise"


class AccesRefuse(ErreurDomaine):
    code = "acces_refuse"


class RessourceIntrouvable(ErreurDomaine):
    code = "ressource_introuvable"


class Conflit(ErreurDomaine):
    code = "conflit"


class TropDeTentatives(ErreurDomaine):
    code = "trop_de_tentatives"

    def __init__(self, message: str, *, reessayer_dans: int, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.reessayer_dans = reessayer_dans
