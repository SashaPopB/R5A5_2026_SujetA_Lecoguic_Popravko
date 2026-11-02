"""Lecture et validation des entrées HTTP avec les DTO pydantic."""
from collections.abc import Sequence
from http import HTTPStatus
from typing import Any, TypeVar

from flask import Response, jsonify, request
from pydantic import BaseModel, ValidationError

from ..domaine.erreurs import DonneesInvalides

M = TypeVar("M", bound=BaseModel)

# Messages pydantic traduits pour l'utilisateur ; les autres gardent le
# message d'origine.
_MESSAGES = {
    "missing": "Champ obligatoire.",
    "extra_forbidden": "Champ non autorisé.",
    "string_too_short": "Trop court.",
    "string_too_long": "Trop long.",
    "string_pattern_mismatch": "Format invalide.",
    "uuid_parsing": "Identifiant invalide.",
    "uuid_type": "Identifiant invalide.",
    "datetime_parsing": "Date et heure invalides (format AAAA-MM-JJTHH:MM).",
    "datetime_from_date_parsing": "Date et heure invalides (format AAAA-MM-JJTHH:MM).",
    "date_parsing": "Date invalide (format AAAA-MM-JJ).",
    "date_from_datetime_parsing": "Date invalide (format AAAA-MM-JJ).",
    "time_parsing": "Heure invalide (format HH:MM).",
    "int_parsing": "Nombre entier attendu.",
    "greater_than_equal": "Valeur trop petite.",
    "less_than_equal": "Valeur trop grande.",
    "enum": "Valeur non autorisée.",
    "literal_error": "Valeur non autorisée.",
    "bool_parsing": "Booléen attendu (true / false).",
}


def traduire_erreurs(erreur: ValidationError) -> list[dict[str, str]]:
    return [
        {
            "champ": ".".join(str(morceau) for morceau in detail["loc"]) or "corps",
            "message": _MESSAGES.get(detail["type"], detail["msg"]),
        }
        for detail in erreur.errors(include_url=False, include_input=False)
    ]


def _valider(modele: type[M], donnees: Any) -> M:
    try:
        return modele.model_validate(donnees)
    except ValidationError as exc:
        raise DonneesInvalides("Données invalides.", code="validation",
                               details=traduire_erreurs(exc)) from exc


def lire_corps(modele: type[M]) -> M:
    """Valide le corps JSON (le Content-Type est contrôlé en amont)."""
    donnees = request.get_json(silent=True)
    if not isinstance(donnees, dict):
        raise DonneesInvalides("Un objet JSON est attendu dans le corps de la requête.",
                               code="corps_invalide")
    return _valider(modele, donnees)


def lire_parametres(modele: type[M]) -> M:
    """Valide les paramètres de la query string (?cle=valeur)."""
    return _valider(modele, request.args.to_dict())


def repondre(contenu: BaseModel | Sequence[BaseModel],
             statut: HTTPStatus = HTTPStatus.OK) -> tuple[Response, HTTPStatus]:
    if isinstance(contenu, BaseModel):
        donnees: Any = contenu.model_dump(mode="json")
    else:
        donnees = [element.model_dump(mode="json") for element in contenu]
    return jsonify(donnees), statut
