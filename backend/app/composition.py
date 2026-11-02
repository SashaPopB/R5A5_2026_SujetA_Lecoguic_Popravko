"""Racine de composition : le seul endroit qui connaît à la fois les cas
d'usage et leurs implémentations concrètes.

Chaque service reçoit ses dépendances par son constructeur (dépôts
SQLAlchemy, transaction, horloge, journal, hachage, diffusion temps réel).
Les petites implémentations qui ne relèvent ni de la base (persistance/) ni
du temps réel (temps_reel.py) sont définies ici. Les contrôleurs récupèrent
les services déjà câblés avec `services()`. Les tests unitaires câblent les
mêmes services avec des dépôts en mémoire.
"""
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from flask import Flask, current_app
from werkzeug.security import check_password_hash, generate_password_hash

from .journalisation import ATTRIBUTS_STANDARD
from .persistance import UniteDeTravailSqlAlchemy
from .persistance.depots import (
    DepotBatimentsSql,
    DepotFermeturesSql,
    DepotReservationsSql,
    DepotSallesSql,
    DepotSessionsSql,
    DepotUtilisateursSql,
    DepotVerrousConnexionSql,
)
from .services.auth import ServiceAuthentification
from .services.contexte import ParametresMetier, PublicationPlanning, Socle
from .services.fermetures import ServiceFermetures
from .services.planning import ServicePlanning
from .services.ports import Diffusion, Horloge
from .services.reservations import ServiceReservations
from .services.salles import ServiceSalles
from .services.utilisateurs import ServiceUtilisateurs

CLE_EXTENSION = "sae.services"


class JournalLogging:
    """Journal d'événements métier branché sur le module logging.

    Le niveau dépend du nom de l'événement (INFO par défaut) : c'est ici, et
    non dans le cas d'usage, qu'on décide qu'un échec de connexion est un
    avertissement. Le format et la destination sont ceux configurés dans
    journalisation.py ; le message est le nom de l'événement, toujours le
    même pour un même fait, et les détails vont dans des champs nommés.
    """

    def __init__(self, nom: str, niveaux: Mapping[str, int] | None = None) -> None:
        self._journal = logging.getLogger(nom)
        self._niveaux = dict(niveaux or {})

    def evenement(self, nom: str, **champs: Any) -> None:
        # Un champ qui porte le nom d'un attribut de LogRecord ferait lever
        # une exception : il est renommé.
        extra = {(cle if cle not in ATTRIBUTS_STANDARD else f"{cle}_"): valeur
                 for cle, valeur in champs.items()}
        self._journal.log(self._niveaux.get(nom, logging.INFO), nom, extra=extra)


class HorlogeFuseau:
    """Heure courante dans le fuseau de l'IUT, jamais celui du serveur (qui
    peut être hébergé dans un autre pays)."""

    def __init__(self, fuseau: ZoneInfo) -> None:
        self._fuseau = fuseau

    def maintenant(self) -> datetime:
        return datetime.now(tz=self._fuseau)


class HacheurWerkzeug:
    """Hachage lent et salé (scrypt) fourni par Werkzeug. L'empreinte contient
    ses paramètres : on peut les durcir plus tard sans invalider les comptes."""

    def hacher(self, mot_de_passe: str) -> str:
        return generate_password_hash(mot_de_passe)

    def verifier(self, empreinte: str, mot_de_passe: str) -> bool:
        return check_password_hash(empreinte, mot_de_passe)


# Événements de sécurité écrits en WARNING : une série de ces lignes doit
# pouvoir déclencher une alerte. Tout le reste est en INFO.
NIVEAUX_SECURITE = {
    "connexion.echec": logging.WARNING,
    "utilisateur.role_modifie": logging.WARNING,
}


@dataclass(frozen=True)
class Services:
    parametres: ParametresMetier
    horloge: Horloge
    auth: ServiceAuthentification
    reservations: ServiceReservations
    salles: ServiceSalles
    fermetures: ServiceFermetures
    planning: ServicePlanning
    utilisateurs: ServiceUtilisateurs


def construire_services(config: Mapping[str, Any], diffusion: Diffusion) -> Services:
    parametres = ParametresMetier.depuis_config(config)
    horloge = HorlogeFuseau(parametres.fuseau)
    socle = Socle(transaction=UniteDeTravailSqlAlchemy(), horloge=horloge,
                  parametres=parametres, journal=JournalLogging("sae.metier"))
    journal_securite = JournalLogging("sae.securite", NIVEAUX_SECURITE)
    publication = PublicationPlanning(diffusion, parametres.fuseau)

    utilisateurs = DepotUtilisateursSql()
    salles = DepotSallesSql()
    reservations = DepotReservationsSql()
    fermetures = DepotFermeturesSql()

    return Services(
        parametres=parametres,
        horloge=horloge,
        auth=ServiceAuthentification(
            socle, utilisateurs=utilisateurs, sessions=DepotSessionsSql(),
            verrous=DepotVerrousConnexionSql(), hacheur=HacheurWerkzeug(),
            journal_securite=journal_securite),
        reservations=ServiceReservations(
            socle, reservations=reservations, salles=salles, fermetures=fermetures,
            utilisateurs=utilisateurs, publication=publication),
        salles=ServiceSalles(socle, salles=salles, batiments=DepotBatimentsSql(),
                             reservations=reservations, publication=publication),
        fermetures=ServiceFermetures(socle, fermetures=fermetures, salles=salles,
                                     reservations=reservations, publication=publication),
        planning=ServicePlanning(parametres, salles=salles, reservations=reservations,
                                 fermetures=fermetures),
        utilisateurs=ServiceUtilisateurs(socle, utilisateurs=utilisateurs,
                                         journal_securite=journal_securite),
    )


def installer_services(app: Flask, diffusion: Diffusion) -> None:
    app.extensions[CLE_EXTENSION] = construire_services(app.config, diffusion)


def services() -> Services:
    """Services de l'application en cours (à appeler dans une requête)."""
    return current_app.extensions[CLE_EXTENSION]
