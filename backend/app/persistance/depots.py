"""Dépôts SQLAlchemy : toutes les requêtes SQL de l'application sont ici.
Chaque classe implémente un contrat de services/ports.py.

Les requêtes de chevauchement utilisent l'expression
tstzrange(debut, fin, '[)') && ... , identique à celle des contraintes
EXCLUDE : PostgreSQL peut alors s'appuyer sur leurs index GiST.
"""
import uuid
from datetime import datetime, time
from typing import Any, TypeVar

from sqlalchemy import ColumnElement, Select, delete, func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from ..domaine.enums import EtatSalle, Role, StatutReservation
from ..extensions import db
from ..services import ports
from ..services.ports import FiltresReservations
from .modeles import (
    Batiment,
    Fermeture,
    Reservation,
    Salle,
    SessionUtilisateur,
    Utilisateur,
    VerrouConnexion,
)

T = TypeVar("T")
_BORNES = literal_column("'[)'")


def _chevauche(modele: type[Reservation] | type[Fermeture], debut: datetime,
               fin: datetime) -> ColumnElement[bool]:
    plage_ligne = func.tstzrange(modele.debut, modele.fin, _BORNES)
    return plage_ligne.op("&&", is_comparison=True)(func.tstzrange(debut, fin, _BORNES))


def _pour_modification(requete: Select[tuple[T]]) -> Select[tuple[T]]:
    """Verrou de ligne (FOR UPDATE) et relecture des valeurs à jour."""
    return requete.with_for_update().execution_options(populate_existing=True)


def _requete_salles() -> Select[tuple[Salle]]:
    return (select(Salle).join(Salle.batiment).options(selectinload(Salle.batiment))
            .order_by(Batiment.code, Salle.code))


def _paginer(requete: Select[tuple[Reservation]], ordre: tuple[Any, ...], page: int,
             taille: int) -> tuple[list[Reservation], int]:
    """Une page de réservations (avec salle et personnes chargées) et le total."""
    total = db.session.scalar(select(func.count()).select_from(requete.subquery())) or 0
    elements = db.session.scalars(
        requete.options(selectinload(Reservation.salle), selectinload(Reservation.titulaire),
                        selectinload(Reservation.annulee_par))
        .order_by(*ordre).limit(taille).offset((page - 1) * taille)
    ).all()
    return list(elements), total


def _motif_like(texte: str) -> str:
    """Échappe % et _ : la recherche porte sur le texte saisi, pas un motif."""
    echappe = texte.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{echappe}%"


class DepotUtilisateursSql:
    def obtenir(self, identifiant: uuid.UUID) -> Utilisateur | None:
        return db.session.get(Utilisateur, identifiant)

    def par_email(self, email: str) -> Utilisateur | None:
        return db.session.scalars(select(Utilisateur).where(Utilisateur.email == email)).first()

    def creer(self, *, email: str, nom: str, prenom: str, role: Role,
              mot_de_passe: str) -> Utilisateur:
        utilisateur = Utilisateur(email=email, nom=nom, prenom=prenom, role=role,
                                  mot_de_passe=mot_de_passe)
        db.session.add(utilisateur)
        return utilisateur

    def verrouiller(self, identifiant: uuid.UUID) -> None:
        """SELECT ... FOR UPDATE : sérialise les réservations d'une même
        personne (sinon deux requêtes simultanées contourneraient A-09)."""
        db.session.execute(
            select(Utilisateur.id).where(Utilisateur.id == identifiant).with_for_update()
        )

    def rechercher(self, recherche: str | None, page: int,
                   taille: int) -> tuple[list[Utilisateur], int]:
        requete = select(Utilisateur)
        if recherche:
            motif = _motif_like(recherche)
            requete = requete.where(or_(
                Utilisateur.email.ilike(motif, escape="\\"),
                Utilisateur.nom.ilike(motif, escape="\\"),
                Utilisateur.prenom.ilike(motif, escape="\\"),
            ))
        total = db.session.scalar(select(func.count()).select_from(requete.subquery())) or 0
        elements = db.session.scalars(
            requete.order_by(Utilisateur.nom, Utilisateur.prenom)
            .limit(taille).offset((page - 1) * taille)
        ).all()
        return list(elements), total


class DepotSessionsSql:
    def creer(self, *, utilisateur_id: uuid.UUID, expire_le: datetime) -> SessionUtilisateur:
        session = SessionUtilisateur(utilisateur_id=utilisateur_id, expire_le=expire_le)
        db.session.add(session)
        db.session.flush()  # l'identifiant de session part dans le jeton
        return session

    def obtenir(self, identifiant: uuid.UUID) -> SessionUtilisateur | None:
        return db.session.get(SessionUtilisateur, identifiant)


class DepotVerrousConnexionSql:
    def obtenir_verrouille(self, email: str) -> VerrouConnexion:
        """Crée la ligne si besoin puis la verrouille : deux essais simultanés
        sur la même adresse sont traités l'un après l'autre."""
        db.session.execute(
            pg_insert(VerrouConnexion).values(email=email, echecs=0)
            .on_conflict_do_nothing(index_elements=[VerrouConnexion.email])
        )
        return db.session.scalars(
            select(VerrouConnexion).where(VerrouConnexion.email == email)
            .with_for_update().execution_options(populate_existing=True)
        ).one()

    def supprimer(self, email: str) -> None:
        db.session.execute(delete(VerrouConnexion).where(VerrouConnexion.email == email))


class DepotBatimentsSql:
    def lister(self) -> list[Batiment]:
        return list(db.session.scalars(select(Batiment).order_by(Batiment.code)))

    def obtenir(self, identifiant: uuid.UUID) -> Batiment | None:
        return db.session.get(Batiment, identifiant)


class DepotSallesSql:
    def lister_toutes(self) -> list[Salle]:
        return list(db.session.scalars(_requete_salles()))

    def lister_proposees(self) -> list[Salle]:
        return list(db.session.scalars(_requete_salles().where(Salle.etat != EtatSalle.RETIREE)))

    def obtenir_pour_modification(self, identifiant: uuid.UUID) -> Salle | None:
        """SELECT ... FOR UPDATE : la ligne reste verrouillée jusqu'au commit."""
        return db.session.scalars(_pour_modification(select(Salle).where(Salle.id == identifiant))
                                  ).first()

    def code_existe(self, code: str) -> bool:
        requete = select(Salle.id).where(func.upper(Salle.code) == code.upper())
        return db.session.scalars(requete).first() is not None

    def creer(self, *, code: str, nom: str | None, batiment_id: uuid.UUID, etage: int,
              capacite: int, heure_ouverture: time, heure_fermeture: time) -> Salle:
        salle = Salle(code=code, nom=nom, batiment_id=batiment_id, etage=etage,
                      capacite=capacite, heure_ouverture=heure_ouverture,
                      heure_fermeture=heure_fermeture, etat=EtatSalle.OUVERTE)
        db.session.add(salle)
        return salle

    def compter_reservations_a_venir(self, salle_ids: list[uuid.UUID],
                                     instant: datetime) -> dict[uuid.UUID, int]:
        if not salle_ids:
            return {}
        lignes = db.session.execute(
            select(Reservation.salle_id, func.count())
            .where(Reservation.salle_id.in_(salle_ids),
                   Reservation.statut == StatutReservation.ACTIVE,
                   Reservation.fin > instant)
            .group_by(Reservation.salle_id)
        )
        return {salle_id: nombre for salle_id, nombre in lignes}


class DepotReservationsSql:
    def creer(self, *, salle_id: uuid.UUID, utilisateur_id: uuid.UUID, debut: datetime,
              fin: datetime, description: str) -> Reservation:
        reservation = Reservation(salle_id=salle_id, utilisateur_id=utilisateur_id,
                                  debut=debut, fin=fin, description=description,
                                  statut=StatutReservation.ACTIVE)
        db.session.add(reservation)
        return reservation

    def obtenir_pour_modification(self, identifiant: uuid.UUID) -> Reservation | None:
        requete = select(Reservation).where(Reservation.id == identifiant)
        return db.session.scalars(_pour_modification(requete)).first()

    def actives_chevauchant(self, debut: datetime, fin: datetime, *,
                            salle_id: uuid.UUID | None = None,
                            utilisateur_id: uuid.UUID | None = None) -> list[Reservation]:
        requete = (
            select(Reservation)
            .options(selectinload(Reservation.titulaire))
            .where(Reservation.statut == StatutReservation.ACTIVE,
                   _chevauche(Reservation, debut, fin))
            .order_by(Reservation.debut)
        )
        if salle_id is not None:
            requete = requete.where(Reservation.salle_id == salle_id)
        if utilisateur_id is not None:
            requete = requete.where(Reservation.utilisateur_id == utilisateur_id)
        return list(db.session.scalars(requete))

    def actives_a_venir_salle(self, salle_id: uuid.UUID, instant: datetime) -> list[Reservation]:
        """Réservations actives d'une salle qui ne sont pas encore terminées."""
        return list(db.session.scalars(
            select(Reservation)
            .where(Reservation.salle_id == salle_id,
                   Reservation.statut == StatutReservation.ACTIVE,
                   Reservation.fin > instant)
            .order_by(Reservation.debut)
        ))

    def a_venir_du_titulaire(self, utilisateur_id: uuid.UUID, instant: datetime, page: int,
                             taille: int) -> tuple[list[Reservation], int]:
        requete = select(Reservation).where(
            Reservation.utilisateur_id == utilisateur_id,
            Reservation.statut == StatutReservation.ACTIVE, Reservation.fin > instant)
        return _paginer(requete, (Reservation.debut,), page, taille)

    def passees_du_titulaire(self, utilisateur_id: uuid.UUID, instant: datetime, page: int,
                             taille: int) -> tuple[list[Reservation], int]:
        requete = select(Reservation).where(
            Reservation.utilisateur_id == utilisateur_id,
            or_(Reservation.statut == StatutReservation.ANNULEE, Reservation.fin <= instant))
        return _paginer(requete, (Reservation.debut.desc(),), page, taille)

    def rechercher(self, filtres: FiltresReservations, page: int,
                   taille: int) -> tuple[list[Reservation], int]:
        requete = select(Reservation)
        if filtres.salle_id is not None:
            requete = requete.where(Reservation.salle_id == filtres.salle_id)
        if filtres.debut_min is not None:
            requete = requete.where(Reservation.debut >= filtres.debut_min)
        if filtres.debut_max is not None:
            requete = requete.where(Reservation.debut < filtres.debut_max)
        if filtres.statut is not None:
            requete = requete.where(Reservation.statut == filtres.statut)
        if filtres.recherche:
            motif = _motif_like(filtres.recherche)
            requete = requete.join(Reservation.titulaire).where(or_(
                Utilisateur.email.ilike(motif, escape="\\"),
                Utilisateur.nom.ilike(motif, escape="\\"),
                Utilisateur.prenom.ilike(motif, escape="\\"),
            ))
        return _paginer(requete, (Reservation.debut.desc(), Reservation.cree_le.desc()),
                        page, taille)

    def sur_periode(self, debut: datetime, fin: datetime) -> list[Reservation]:
        """Toutes les réservations (actives et annulées) commençant dans la
        période, pour l'export d'archivage."""
        return list(db.session.scalars(
            select(Reservation)
            .options(selectinload(Reservation.salle).selectinload(Salle.batiment),
                     selectinload(Reservation.titulaire),
                     selectinload(Reservation.annulee_par))
            .where(Reservation.debut >= debut, Reservation.debut < fin)
            .order_by(Reservation.debut, Reservation.cree_le)
        ))


class DepotFermeturesSql:
    def creer(self, *, salle_id: uuid.UUID, debut: datetime, fin: datetime, motif: str,
              cree_par_id: uuid.UUID) -> Fermeture:
        fermeture = Fermeture(salle_id=salle_id, debut=debut, fin=fin, motif=motif,
                              cree_par_id=cree_par_id)
        db.session.add(fermeture)
        return fermeture

    def obtenir(self, identifiant: uuid.UUID) -> Fermeture | None:
        return db.session.get(Fermeture, identifiant)

    def supprimer(self, fermeture: ports.Fermeture) -> None:
        # Reçoit l'objet chargé par obtenir() : un modèle de cette session.
        db.session.delete(fermeture)

    def chevauchant(self, debut: datetime, fin: datetime, *,
                    salle_id: uuid.UUID | None = None) -> list[Fermeture]:
        requete = (select(Fermeture).where(_chevauche(Fermeture, debut, fin))
                   .order_by(Fermeture.debut))
        if salle_id is not None:
            requete = requete.where(Fermeture.salle_id == salle_id)
        return list(db.session.scalars(requete))
