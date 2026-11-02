"""Contrats dont dépendent les cas d'usage (inversion de dépendance).

Les services ne connaissent ni SQLAlchemy, ni Flask, ni le module logging :
ils reçoivent, à la construction, des objets qui respectent ces contrats.
Les implémentations vivent à la périphérie (persistance/, temps_reel.py) ou
dans composition.py, qui les câble au démarrage. En test,
on passe des implémentations en mémoire : aucune base n'est nécessaire.

Les contrats sont des `Protocol` : une classe les respecte par sa forme,
sans en hériter (les modèles SQLAlchemy conviennent tels quels).
"""
import uuid
from collections.abc import Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, time
from typing import Any, Protocol

from ..domaine.enums import EtatSalle, Role, StatutReservation
from ..domaine.erreurs import ErreurDomaine

# --------------------------------------------------------------- entités
# Attributs lus ou modifiés par les cas d'usage, et relations lues par la
# couche API pour présenter un résultat (salle d'une réservation, titulaire).


class Utilisateur(Protocol):
    id: uuid.UUID
    email: str
    nom: str
    prenom: str
    role: Role
    mot_de_passe: str

    @property
    def nom_complet(self) -> str: ...


class SessionUtilisateur(Protocol):
    id: uuid.UUID
    utilisateur_id: uuid.UUID
    expire_le: datetime
    revoquee_le: datetime | None


class VerrouConnexion(Protocol):
    email: str
    echecs: int
    dernier_echec: datetime
    bloque_jusqu_a: datetime | None


class Batiment(Protocol):
    id: uuid.UUID
    code: str
    nom: str


class Salle(Protocol):
    id: uuid.UUID
    code: str
    nom: str | None
    batiment_id: uuid.UUID
    etage: int
    capacite: int
    heure_ouverture: time
    heure_fermeture: time
    etat: EtatSalle
    batiment: Batiment


class Reservation(Protocol):
    id: uuid.UUID
    salle_id: uuid.UUID
    utilisateur_id: uuid.UUID
    debut: datetime
    fin: datetime
    description: str
    statut: StatutReservation
    annulee_le: datetime | None
    annulee_par_id: uuid.UUID | None
    motif_annulation: str | None
    cree_le: datetime
    salle: Salle
    titulaire: Utilisateur
    annulee_par: Utilisateur | None


class Fermeture(Protocol):
    id: uuid.UUID
    salle_id: uuid.UUID
    debut: datetime
    fin: datetime
    motif: str


@dataclass(frozen=True)
class FiltresReservations:
    """Critères de l'historique (A-08), déjà convertis en instants."""

    salle_id: uuid.UUID | None = None
    debut_min: datetime | None = None
    debut_max: datetime | None = None  # exclu
    statut: StatutReservation | None = None
    recherche: str | None = None


# --------------------------------------------------------------- dépôts


class DepotUtilisateurs(Protocol):
    def obtenir(self, identifiant: uuid.UUID) -> Utilisateur | None: ...

    def par_email(self, email: str) -> Utilisateur | None: ...

    def creer(self, *, email: str, nom: str, prenom: str, role: Role,
              mot_de_passe: str) -> Utilisateur: ...

    def verrouiller(self, identifiant: uuid.UUID) -> None: ...

    def rechercher(self, recherche: str | None, page: int,
                   taille: int) -> tuple[Sequence[Utilisateur], int]: ...


class DepotSessions(Protocol):
    def creer(self, *, utilisateur_id: uuid.UUID, expire_le: datetime) -> SessionUtilisateur: ...

    def obtenir(self, identifiant: uuid.UUID) -> SessionUtilisateur | None: ...


class DepotVerrousConnexion(Protocol):
    def obtenir_verrouille(self, email: str) -> VerrouConnexion: ...

    def supprimer(self, email: str) -> None: ...


class DepotBatiments(Protocol):
    def lister(self) -> Sequence[Batiment]: ...

    def obtenir(self, identifiant: uuid.UUID) -> Batiment | None: ...


class DepotSalles(Protocol):
    def lister_proposees(self) -> Sequence[Salle]: ...

    def lister_toutes(self) -> Sequence[Salle]: ...

    def obtenir_pour_modification(self, identifiant: uuid.UUID) -> Salle | None: ...

    def code_existe(self, code: str) -> bool: ...

    def creer(self, *, code: str, nom: str | None, batiment_id: uuid.UUID, etage: int,
              capacite: int, heure_ouverture: time, heure_fermeture: time) -> Salle: ...

    def compter_reservations_a_venir(self, salle_ids: list[uuid.UUID],
                                     instant: datetime) -> dict[uuid.UUID, int]: ...


class DepotReservations(Protocol):
    def creer(self, *, salle_id: uuid.UUID, utilisateur_id: uuid.UUID, debut: datetime,
              fin: datetime, description: str) -> Reservation: ...

    def obtenir_pour_modification(self, identifiant: uuid.UUID) -> Reservation | None: ...

    def actives_chevauchant(self, debut: datetime, fin: datetime, *,
                            salle_id: uuid.UUID | None = None,
                            utilisateur_id: uuid.UUID | None = None) -> Sequence[Reservation]: ...

    def actives_a_venir_salle(self, salle_id: uuid.UUID,
                              instant: datetime) -> Sequence[Reservation]: ...

    def a_venir_du_titulaire(self, utilisateur_id: uuid.UUID, instant: datetime, page: int,
                             taille: int) -> tuple[Sequence[Reservation], int]: ...

    def passees_du_titulaire(self, utilisateur_id: uuid.UUID, instant: datetime, page: int,
                             taille: int) -> tuple[Sequence[Reservation], int]: ...

    def rechercher(self, filtres: FiltresReservations, page: int,
                   taille: int) -> tuple[Sequence[Reservation], int]: ...

    def sur_periode(self, debut: datetime, fin: datetime) -> Sequence[Reservation]: ...


class DepotFermetures(Protocol):
    def creer(self, *, salle_id: uuid.UUID, debut: datetime, fin: datetime, motif: str,
              cree_par_id: uuid.UUID) -> Fermeture: ...

    def obtenir(self, identifiant: uuid.UUID) -> Fermeture | None: ...

    def supprimer(self, fermeture: Fermeture) -> None: ...

    def chevauchant(self, debut: datetime, fin: datetime, *,
                    salle_id: uuid.UUID | None = None) -> Sequence[Fermeture]: ...


# ---------------------------------------------------- outils transverses


class UniteDeTravail(Protocol):
    """Transaction en cours : valider, et traduire une violation de contrainte
    de la base (connue par son nom) en erreur métier. En cas d'erreur, le
    gestionnaire d'erreurs de l'API annule la transaction."""

    def valider(self) -> None: ...

    def traduire_contraintes(
        self, erreurs: Mapping[str, ErreurDomaine]) -> AbstractContextManager[None]: ...


class Horloge(Protocol):
    def maintenant(self) -> datetime: ...


class Journal(Protocol):
    """Événements métier. Le cas d'usage nomme l'événement et donne des
    champs ; le niveau, le format et la destination sont décidés par
    l'implémentation (voir composition.JournalLogging)."""

    def evenement(self, nom: str, **champs: Any) -> None: ...


class Diffusion(Protocol):
    """Canal temps réel vers les clients connectés (A-04)."""

    def publier(self, evenement: dict[str, Any]) -> None: ...


class HacheurMotDePasse(Protocol):
    def hacher(self, mot_de_passe: str) -> str: ...

    def verifier(self, empreinte: str, mot_de_passe: str) -> bool: ...
