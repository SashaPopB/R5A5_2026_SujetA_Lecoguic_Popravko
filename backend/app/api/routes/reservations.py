"""Réservations : création, annulation, suivi, historique et export."""
import uuid
from collections.abc import Sequence
from http import HTTPStatus

from flask import Blueprint, Response

from ...composition import services
from ...domaine.enums import Role
from ...services import export as service_export
from ...services.ports import Reservation
from ...services.reservations import CriteresHistorique, DemandeReservation, Pagination
from .. import dto, mappers
from ..openapi import documenter
from ..securite import acteur_courant, roles_requis
from ..validation import lire_corps, lire_parametres, repondre

bp = Blueprint("reservations", __name__, url_prefix="/api")
TAGS = ("Réservations",)


def _page(elements: Sequence[Reservation], total: int,
          pagination: Pagination) -> dto.PageReservationsSortie:
    fuseau = services().parametres.fuseau
    return dto.PageReservationsSortie(
        elements=[mappers.reservation(r, fuseau) for r in elements],
        total=total, page=pagination.page, taille=pagination.taille)


@bp.post("/reservations")
@documenter("Réserver une salle", tags=TAGS, corps=dto.ReservationEntree,
            reponses={201: dto.ReservationSortie},
            erreurs=(HTTPStatus.NOT_FOUND, HTTPStatus.CONFLICT),
            description="Heures pleines, un seul jour, dans les horaires de la salle. "
                        "409 si le créneau est déjà pris ou fermé (A-03). 403 si un étudiant "
                        "dépasse 2 h d'affilée (A-09) ou si le gestionnaire tente de réserver.")
@roles_requis(Role.ETUDIANT, Role.ENSEIGNANT)
def creer_reservation():
    entree = lire_corps(dto.ReservationEntree)
    reservation = services().reservations.creer(
        acteur_courant(),
        DemandeReservation(entree.salle_id, entree.debut, entree.fin, entree.description))
    return repondre(mappers.reservation(reservation, services().parametres.fuseau),
                    HTTPStatus.CREATED)


@bp.get("/reservations")
@documenter("Suivi et historique des réservations", tags=TAGS,
            parametres=dto.HistoriqueParametres, reponses={200: dto.PageReservationsSortie},
            description="A-08 : qui a réservé ou annulé un créneau, et quand. Filtres "
                        "combinables, résultats paginés (plus récents d'abord).")
@roles_requis(Role.GESTIONNAIRE)
def rechercher_reservations():
    p = lire_parametres(dto.HistoriqueParametres)
    pagination = Pagination(p.page, p.taille)
    elements, total = services().reservations.rechercher(
        CriteresHistorique(p.salle_id, p.du, p.au, p.statut, p.recherche), pagination)
    return repondre(_page(elements, total, pagination))


@bp.get("/reservations/export")
@documenter("Exporter les réservations d'une période en CSV", tags=TAGS,
            parametres=dto.ExportParametres, type_contenu="text/csv",
            reponses={200: "Fichier CSV (séparateur « ; », UTF-8 avec BOM)"},
            erreurs=(HTTPStatus.TOO_MANY_REQUESTS,),
            description="A-10 : réservations actives et annulées commençant entre `du` et "
                        "`au` (inclus), avec l'historique d'annulation. 366 jours maximum.")
@roles_requis(Role.GESTIONNAIRE)
def exporter_reservations():
    p = lire_parametres(dto.ExportParametres)
    fuseau = services().parametres.fuseau
    reservations = services().reservations.de_la_periode(p.du, p.au)
    contenu = service_export.generer_csv(service_export.vers_ligne(r, fuseau)
                                         for r in reservations)
    nom_fichier = f"reservations_{p.du.isoformat()}_{p.au.isoformat()}.csv"
    return Response(contenu, mimetype="text/csv", headers={
        "Content-Disposition": f'attachment; filename="{nom_fichier}"',
    })


@bp.patch("/reservations/<uuid:reservation_id>")
@documenter("Annuler une réservation", tags=TAGS, corps=dto.AnnulationEntree,
            reponses={200: dto.ReservationSortie},
            erreurs=(HTTPStatus.FORBIDDEN, HTTPStatus.NOT_FOUND, HTTPStatus.CONFLICT),
            description="Seule transition permise : active -> annulee. Le titulaire annule "
                        "les siennes (A-05), le gestionnaire celles de tout le monde (A-06). "
                        "La réservation reste dans l'historique.")
def annuler_reservation(reservation_id: uuid.UUID):
    entree = lire_corps(dto.AnnulationEntree)
    reservation = services().reservations.annuler(acteur_courant(), reservation_id,
                                                  entree.motif)
    return repondre(mappers.reservation(reservation, services().parametres.fuseau))


@bp.get("/moi/reservations")
@documenter("Mes réservations", tags=TAGS, parametres=dto.MesReservationsParametres,
            reponses={200: dto.PageReservationsSortie},
            description="`a_venir` : actives non terminées, les plus proches d'abord ; "
                        "`passees` : terminées ou annulées, les plus récentes d'abord. "
                        "Paginé (20 par page par défaut, 100 au maximum).")
def mes_reservations():
    p = lire_parametres(dto.MesReservationsParametres)
    pagination = Pagination(p.page, p.taille)
    service = services().reservations
    lister = service.a_venir if p.periode == "a_venir" else service.historique
    elements, total = lister(acteur_courant(), pagination)
    return repondre(_page(elements, total, pagination))
