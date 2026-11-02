"""Modèles SQLAlchemy (objets d'accès aux données), calqués sur db/schema.sql.

Le schéma SQL reste la source de vérité : ces classes ne créent aucune
table (pas de create_all), elles décrivent simplement les colonnes.
"""
import uuid
from datetime import datetime, time
from enum import Enum

from sqlalchemy import ForeignKey, Text, Time, func
from sqlalchemy.dialects.postgresql import ENUM, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..domaine.enums import EtatSalle, Role, StatutReservation
from ..extensions import db


def _valeurs(enumeration: type[Enum]) -> list[str]:
    """Stocke la valeur (« etudiant ») et non le nom Python (« ETUDIANT »)."""
    return [membre.value for membre in enumeration]


RoleSql = ENUM(Role, name="role_utilisateur", create_type=False, values_callable=_valeurs)
EtatSalleSql = ENUM(EtatSalle, name="etat_salle", create_type=False, values_callable=_valeurs)
StatutSql = ENUM(StatutReservation, name="statut_reservation", create_type=False,
                 values_callable=_valeurs)
Horodatage = TIMESTAMP(timezone=True)


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class Utilisateur(db.Model):
    __tablename__ = "utilisateur"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(Text, unique=True)
    mot_de_passe: Mapped[str] = mapped_column(Text)
    nom: Mapped[str] = mapped_column(Text)
    prenom: Mapped[str] = mapped_column(Text)
    role: Mapped[Role] = mapped_column(RoleSql, default=Role.ETUDIANT)
    cree_le: Mapped[datetime] = mapped_column(Horodatage, server_default=func.now())

    @property
    def nom_complet(self) -> str:
        return f"{self.prenom} {self.nom}"


class SessionUtilisateur(db.Model):
    __tablename__ = "session_utilisateur"

    id: Mapped[uuid.UUID] = _uuid_pk()
    utilisateur_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utilisateur.id"))
    cree_le: Mapped[datetime] = mapped_column(Horodatage, server_default=func.now())
    expire_le: Mapped[datetime] = mapped_column(Horodatage)
    revoquee_le: Mapped[datetime | None] = mapped_column(Horodatage)


class VerrouConnexion(db.Model):
    __tablename__ = "verrou_connexion"

    email: Mapped[str] = mapped_column(Text, primary_key=True)
    echecs: Mapped[int] = mapped_column(default=0)
    dernier_echec: Mapped[datetime] = mapped_column(Horodatage, server_default=func.now())
    bloque_jusqu_a: Mapped[datetime | None] = mapped_column(Horodatage)


class Batiment(db.Model):
    __tablename__ = "batiment"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(Text, unique=True)
    nom: Mapped[str] = mapped_column(Text)


class Salle(db.Model):
    __tablename__ = "salle"

    id: Mapped[uuid.UUID] = _uuid_pk()
    code: Mapped[str] = mapped_column(Text)
    nom: Mapped[str | None] = mapped_column(Text)
    batiment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("batiment.id"))
    etage: Mapped[int] = mapped_column(default=0)
    capacite: Mapped[int]
    heure_ouverture: Mapped[time] = mapped_column(Time, default=time(8))
    heure_fermeture: Mapped[time] = mapped_column(Time, default=time(20))
    etat: Mapped[EtatSalle] = mapped_column(EtatSalleSql, default=EtatSalle.OUVERTE)

    batiment: Mapped[Batiment] = relationship()


class Reservation(db.Model):
    __tablename__ = "reservation"

    id: Mapped[uuid.UUID] = _uuid_pk()
    salle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("salle.id"))
    utilisateur_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("utilisateur.id"))
    debut: Mapped[datetime] = mapped_column(Horodatage)
    fin: Mapped[datetime] = mapped_column(Horodatage)
    description: Mapped[str] = mapped_column(Text)
    statut: Mapped[StatutReservation] = mapped_column(StatutSql, default=StatutReservation.ACTIVE)
    cree_le: Mapped[datetime] = mapped_column(Horodatage, server_default=func.now())
    annulee_le: Mapped[datetime | None] = mapped_column(Horodatage)
    annulee_par_id: Mapped[uuid.UUID | None] = mapped_column(
        "annulee_par", ForeignKey("utilisateur.id")
    )
    motif_annulation: Mapped[str | None] = mapped_column(Text)

    salle: Mapped[Salle] = relationship()
    titulaire: Mapped[Utilisateur] = relationship(foreign_keys=[utilisateur_id])
    annulee_par: Mapped[Utilisateur | None] = relationship(foreign_keys=[annulee_par_id])


class Fermeture(db.Model):
    __tablename__ = "fermeture"

    id: Mapped[uuid.UUID] = _uuid_pk()
    salle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("salle.id"))
    debut: Mapped[datetime] = mapped_column(Horodatage)
    fin: Mapped[datetime] = mapped_column(Horodatage)
    motif: Mapped[str] = mapped_column(Text)
    cree_par_id: Mapped[uuid.UUID] = mapped_column("cree_par", ForeignKey("utilisateur.id"))
    cree_le: Mapped[datetime] = mapped_column(Horodatage, server_default=func.now())

    salle: Mapped[Salle] = relationship()
