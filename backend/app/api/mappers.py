"""Conversion des entités renvoyées par les services vers les DTO de sortie
(projection explicite : seuls les champs listés ici sortent de l'API).

Les horodatages sont convertis dans le fuseau de l'IUT : le client reçoit
« 2026-11-02T10:00:00+01:00 », lisible et sans ambiguïté.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

from ..services.planning import Planning, ReservationVue
from ..services.ports import Batiment, Fermeture, Reservation, Salle, Utilisateur
from . import dto


def _local(instant: datetime, fuseau: ZoneInfo) -> datetime:
    return instant.astimezone(fuseau)


def utilisateur(entite: Utilisateur) -> dto.UtilisateurSortie:
    return dto.UtilisateurSortie(id=entite.id, email=entite.email, nom=entite.nom,
                                 prenom=entite.prenom, role=entite.role)


def personne(entite: Utilisateur) -> dto.PersonneSortie:
    return dto.PersonneSortie(id=entite.id, nom=entite.nom, prenom=entite.prenom,
                              email=entite.email, role=entite.role)


def batiment(entite: Batiment) -> dto.BatimentSortie:
    return dto.BatimentSortie(id=entite.id, code=entite.code, nom=entite.nom)


def salle(entite: Salle, reservations_a_venir: int | None = None) -> dto.SalleSortie:
    return dto.SalleSortie(
        id=entite.id, code=entite.code, nom=entite.nom, batiment=batiment(entite.batiment),
        etage=entite.etage, capacite=entite.capacite,
        heure_ouverture=entite.heure_ouverture, heure_fermeture=entite.heure_fermeture,
        etat=entite.etat, reservations_a_venir=reservations_a_venir,
    )


def salle_modifiee(entite: Salle, reservations_a_venir: int,
                   reservations_annulees: int) -> dto.SalleModifieeSortie:
    return dto.SalleModifieeSortie(
        **salle(entite, reservations_a_venir).model_dump(),
        reservations_annulees=reservations_annulees,
    )


def fermeture(entite: Fermeture, fuseau: ZoneInfo) -> dto.FermetureSortie:
    return dto.FermetureSortie(id=entite.id, salle_id=entite.salle_id,
                               debut=_local(entite.debut, fuseau),
                               fin=_local(entite.fin, fuseau), motif=entite.motif)


def reservation(entite: Reservation, fuseau: ZoneInfo) -> dto.ReservationSortie:
    return dto.ReservationSortie(
        id=entite.id,
        salle=dto.SalleResume(id=entite.salle.id, code=entite.salle.code, nom=entite.salle.nom),
        debut=_local(entite.debut, fuseau),
        fin=_local(entite.fin, fuseau),
        description=entite.description,
        statut=entite.statut,
        titulaire=personne(entite.titulaire),
        cree_le=_local(entite.cree_le, fuseau),
        annulee_le=_local(entite.annulee_le, fuseau) if entite.annulee_le else None,
        annulee_par=personne(entite.annulee_par) if entite.annulee_par else None,
        motif_annulation=entite.motif_annulation,
    )


def reservation_planning(vue: ReservationVue, fuseau: ZoneInfo) -> dto.ReservationPlanningSortie:
    entite = vue.reservation
    return dto.ReservationPlanningSortie(
        id=entite.id,
        salle_id=entite.salle_id,
        debut=_local(entite.debut, fuseau),
        fin=_local(entite.fin, fuseau),
        est_a_moi=vue.est_a_moi,
        titulaire=personne(entite.titulaire) if vue.details_visibles else None,
        description=entite.description if vue.details_visibles else None,
    )


def planning(vue: Planning, fuseau: ZoneInfo) -> dto.PlanningSortie:
    return dto.PlanningSortie(
        date=vue.jour,
        jour_ouvert=vue.jour_ouvert,
        salles=[salle(s) for s in vue.salles],
        reservations=[reservation_planning(r, fuseau) for r in vue.reservations],
        fermetures=[fermeture(f, fuseau) for f in vue.fermetures],
    )
