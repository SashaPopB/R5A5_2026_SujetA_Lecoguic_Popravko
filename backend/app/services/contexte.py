"""Ce que tous les cas d'usage partagent : paramètres métier, outils
transverses, contrôle du rôle gestionnaire et publication des changements
du planning."""
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..domaine.enums import Role
from ..domaine.erreurs import AccesRefuse
from .ports import Diffusion, Horloge, Journal, UniteDeTravail


def exiger_gestionnaire(role: Role) -> None:
    """Les routes vérifient déjà le rôle (@roles_requis) ; les services le
    revérifient. Ce doublon est voulu : un service reste sûr même appelé
    depuis une future route qui oublierait le décorateur."""
    if role != Role.GESTIONNAIRE:
        raise AccesRefuse("Action réservée au gestionnaire.", code="role_insuffisant")


@dataclass(frozen=True)
class ParametresMetier:
    fuseau: ZoneInfo
    jours_ouverture: frozenset[int]
    horizon_jours: int
    duree_max_etudiant: timedelta
    description_longueur_max: int
    export_periode_max_jours: int
    connexion_essais_libres: int
    connexion_delai_initial: timedelta
    connexion_delai_max: timedelta
    duree_session: timedelta

    @classmethod
    def depuis_config(cls, config: Mapping[str, Any]) -> "ParametresMetier":
        """Lu une seule fois, au démarrage (composition.py)."""
        return cls(
            fuseau=ZoneInfo(config["FUSEAU_HORAIRE"]),
            jours_ouverture=frozenset(config["JOURS_OUVERTURE"]),
            horizon_jours=config["HORIZON_RESERVATION_JOURS"],
            duree_max_etudiant=config["DUREE_MAX_ETUDIANT"],
            description_longueur_max=config["DESCRIPTION_LONGUEUR_MAX"],
            export_periode_max_jours=config["EXPORT_PERIODE_MAX_JOURS"],
            connexion_essais_libres=config["CONNEXION_ESSAIS_LIBRES"],
            connexion_delai_initial=config["CONNEXION_DELAI_INITIAL"],
            connexion_delai_max=config["CONNEXION_DELAI_MAX"],
            duree_session=config["JWT_REFRESH_TOKEN_EXPIRES"],
        )


@dataclass(frozen=True)
class Socle:
    """Outils transverses reçus par chaque service (regroupés pour garder des
    constructeurs courts)."""

    transaction: UniteDeTravail
    horloge: Horloge
    parametres: ParametresMetier
    journal: Journal


class PublicationPlanning:
    """Traduit un changement validé en événement temps réel (A-04).

    L'événement ne contient que le type de changement, la salle et les jours
    touchés : aucune donnée personnelle ne part dans le flux. Le client
    recharge ensuite le planning par l'API, qui applique les règles de
    visibilité. À appeler uniquement APRÈS le commit.
    """

    def __init__(self, diffusion: Diffusion, fuseau: ZoneInfo) -> None:
        self._diffusion = diffusion
        self._fuseau = fuseau

    def creneau_modifie(self, salle_id: uuid.UUID, debut: datetime, fin: datetime) -> None:
        premier = debut.astimezone(self._fuseau).date()
        dernier = (fin - timedelta(microseconds=1)).astimezone(self._fuseau).date()
        jours = [(premier + timedelta(days=n)).isoformat()
                 for n in range((dernier - premier).days + 1)]
        self._diffusion.publier({"type": "planning", "salle_id": str(salle_id), "jours": jours})

    def salles_modifiees(self) -> None:
        self._diffusion.publier({"type": "salles"})
