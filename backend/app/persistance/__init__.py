"""Couche de persistance : modèles SQLAlchemy, dépôts (repositories) et
transaction. Ce sont les implémentations des contrats de services/ports.py ;
les services n'écrivent aucune requête SQL et n'importent rien d'ici.
"""
import re
from collections.abc import Iterator, Mapping
from contextlib import contextmanager

from sqlalchemy.exc import IntegrityError

from ..domaine.erreurs import ErreurDomaine
from ..extensions import db

_NOM_CONTRAINTE = re.compile(r'constraint "([^"]+)"')


def nom_contrainte(erreur: IntegrityError) -> str:
    """Nom de la contrainte violée, quel que soit le pilote PostgreSQL."""
    diag = getattr(erreur.orig, "diag", None)
    nom = getattr(diag, "constraint_name", None)
    if nom:
        return str(nom)
    correspondance = _NOM_CONTRAINTE.search(str(erreur.orig))
    return correspondance.group(1) if correspondance else ""


class UniteDeTravailSqlAlchemy:
    """Transaction de la requête en cours (session SQLAlchemy de Flask)."""

    def valider(self) -> None:
        db.session.commit()

    @contextmanager
    def traduire_contraintes(self, erreurs: Mapping[str, ErreurDomaine]) -> Iterator[None]:
        """Transforme une violation de contrainte connue en erreur métier.

        Le bloc est suivi d'un flush pour que PostgreSQL vérifie les
        contraintes tout de suite (et non au commit, où l'on ne saurait plus
        quoi répondre).
        """
        try:
            yield
            db.session.flush()
        except IntegrityError as exc:
            db.session.rollback()
            erreur_metier = erreurs.get(nom_contrainte(exc))
            if erreur_metier is None:
                raise
            raise erreur_metier from exc
