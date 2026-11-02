"""Cas d'usage autour des réservations (A-02, A-03, A-05, A-06, A-08, A-09, A-10)."""
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from ..domaine.creneaux import (
    Intervalle,
    bornes_journee,
    construire_creneau,
    verifier_horaires_salle,
    verifier_horizon,
    verifier_jour_ouvert,
    verifier_limite_etudiant,
    verifier_non_passe,
)
from ..domaine.description import normaliser_description
from ..domaine.enums import ROLES_QUI_RESERVENT, EtatSalle, Role, StatutReservation
from ..domaine.erreurs import AccesRefuse, Conflit, DonneesInvalides, RessourceIntrouvable
from .contexte import PublicationPlanning, Socle
from .ports import (
    DepotFermetures,
    DepotReservations,
    DepotSalles,
    DepotUtilisateurs,
    FiltresReservations,
    Reservation,
    Utilisateur,
)


@dataclass(frozen=True)
class DemandeReservation:
    salle_id: uuid.UUID
    debut: datetime
    fin: datetime
    description: str


@dataclass(frozen=True)
class CriteresHistorique:
    salle_id: uuid.UUID | None = None
    du: date | None = None
    au: date | None = None  # inclus
    statut: StatutReservation | None = None
    recherche: str | None = None


@dataclass(frozen=True)
class Pagination:
    page: int = 1
    taille: int = 20


def annuler_toutes(reservations: Iterable[Reservation], *, par: uuid.UUID, instant: datetime,
                   motif: str | None) -> None:
    """Passe des réservations à l'état annulé, sans les supprimer : elles
    restent dans l'historique (A-08). Le commit revient à l'appelant."""
    for reservation in reservations:
        reservation.statut = StatutReservation.ANNULEE
        reservation.annulee_le = instant
        reservation.annulee_par_id = par
        reservation.motif_annulation = motif or None


def verifier_titulaire_ou_gestionnaire(acteur: Utilisateur, reservation: Reservation) -> None:
    """Contrôle de propriété, fait APRÈS le chargement de la ressource."""
    if reservation.utilisateur_id != acteur.id and acteur.role != Role.GESTIONNAIRE:
        raise AccesRefuse("Vous ne pouvez annuler que vos propres réservations.",
                          code="reservation_d_un_autre")


class ServiceReservations:
    def __init__(self, socle: Socle, *, reservations: DepotReservations, salles: DepotSalles,
                 fermetures: DepotFermetures, utilisateurs: DepotUtilisateurs,
                 publication: PublicationPlanning) -> None:
        self._socle = socle
        self._reservations = reservations
        self._salles = salles
        self._fermetures = fermetures
        self._utilisateurs = utilisateurs
        self._publication = publication

    def creer(self, acteur: Utilisateur, demande: DemandeReservation) -> Reservation:
        reglages = self._socle.parametres
        instant = self._socle.horloge.maintenant()

        if acteur.role not in ROLES_QUI_RESERVENT:
            raise AccesRefuse("Le gestionnaire ne réserve pas : il ferme des créneaux.",
                              code="role_sans_reservation")

        creneau = construire_creneau(demande.debut, demande.fin, reglages.fuseau)
        verifier_jour_ouvert(creneau.debut.date(), reglages.jours_ouverture)
        verifier_non_passe(creneau, instant)
        verifier_horizon(creneau, instant, reglages.horizon_jours)
        description = normaliser_description(demande.description,
                                             reglages.description_longueur_max)

        # Verrous toujours pris dans le même ordre (personne puis salle) pour
        # éviter les interblocages entre cas d'usage concurrents.
        self._utilisateurs.verrouiller(acteur.id)
        salle = self._salles.obtenir_pour_modification(demande.salle_id)
        if salle is None or salle.etat == EtatSalle.RETIREE:
            raise RessourceIntrouvable("Salle inconnue.", code="salle_introuvable")
        if salle.etat != EtatSalle.OUVERTE:
            raise Conflit(f"La salle {salle.code} est fermée.", code="salle_fermee")
        verifier_horaires_salle(creneau, salle.heure_ouverture, salle.heure_fermeture)

        if self._fermetures.chevauchant(creneau.debut, creneau.fin, salle_id=salle.id):
            raise Conflit("Ce créneau a été fermé par le gestionnaire.", code="creneau_ferme")
        if self._reservations.actives_chevauchant(creneau.debut, creneau.fin, salle_id=salle.id):
            raise Conflit(f"La salle {salle.code} est déjà réservée sur ce créneau.",
                          code="creneau_deja_reserve")
        if self._reservations.actives_chevauchant(creneau.debut, creneau.fin,
                                                  utilisateur_id=acteur.id):
            raise Conflit("Vous avez déjà une réservation sur ce créneau.",
                          code="reservation_simultanee")
        if acteur.role == Role.ETUDIANT:
            self._verifier_limite_etudiant(acteur, creneau)

        # Les contraintes EXCLUDE de la base restent le dernier rempart si deux
        # requêtes passent les vérifications ci-dessus au même instant.
        with self._socle.transaction.traduire_contraintes({
            "reservation_sans_chevauchement_salle": Conflit(
                f"La salle {salle.code} est déjà réservée sur ce créneau.",
                code="creneau_deja_reserve"),
            "reservation_sans_chevauchement_utilisateur": Conflit(
                "Vous avez déjà une réservation sur ce créneau.", code="reservation_simultanee"),
        }):
            reservation = self._reservations.creer(
                salle_id=salle.id, utilisateur_id=acteur.id, debut=creneau.debut,
                fin=creneau.fin, description=description)
        self._socle.transaction.valider()

        self._socle.journal.evenement(
            "reservation.creee", reservation=str(reservation.id), salle=str(salle.id),
            utilisateur=str(acteur.id), debut=creneau.debut.isoformat(),
            fin=creneau.fin.isoformat())
        self._publication.creneau_modifie(salle.id, creneau.debut, creneau.fin)
        return reservation

    def _verifier_limite_etudiant(self, acteur: Utilisateur, creneau: Intervalle) -> None:
        reglages = self._socle.parametres
        journee = bornes_journee(creneau.debut.date(), reglages.fuseau)
        du_jour = self._reservations.actives_chevauchant(journee.debut, journee.fin,
                                                         utilisateur_id=acteur.id)
        verifier_limite_etudiant(creneau, [Intervalle(r.debut, r.fin) for r in du_jour],
                                 reglages.duree_max_etudiant)

    def annuler(self, acteur: Utilisateur, reservation_id: uuid.UUID,
                motif: str | None = None) -> Reservation:
        """A-05 : chacun annule ses réservations ; A-06 : seul le gestionnaire
        annule celles des autres."""
        reservation = self._reservations.obtenir_pour_modification(reservation_id)
        if reservation is None:
            raise RessourceIntrouvable("Réservation introuvable.", code="reservation_introuvable")
        verifier_titulaire_ou_gestionnaire(acteur, reservation)
        if reservation.statut == StatutReservation.ANNULEE:
            raise Conflit("Cette réservation est déjà annulée.", code="deja_annulee")
        instant = self._socle.horloge.maintenant()
        if reservation.fin <= instant:
            raise Conflit("Une réservation terminée ne s'annule plus : elle fait partie de "
                          "l'historique.", code="reservation_terminee")

        annuler_toutes([reservation], par=acteur.id, instant=instant, motif=motif)
        self._socle.transaction.valider()
        self._socle.journal.evenement(
            "reservation.annulee", reservation=str(reservation.id),
            salle=str(reservation.salle_id), utilisateur=str(acteur.id),
            par_gestionnaire=acteur.id != reservation.utilisateur_id)
        self._publication.creneau_modifie(reservation.salle_id, reservation.debut,
                                          reservation.fin)
        return reservation

    def a_venir(self, acteur: Utilisateur,
                pagination: Pagination) -> tuple[Sequence[Reservation], int]:
        """Réservations actives pas encore terminées, les plus proches d'abord."""
        return self._reservations.a_venir_du_titulaire(
            acteur.id, self._socle.horloge.maintenant(), pagination.page, pagination.taille)

    def historique(self, acteur: Utilisateur,
                   pagination: Pagination) -> tuple[Sequence[Reservation], int]:
        """Réservations terminées ou annulées, les plus récentes d'abord."""
        return self._reservations.passees_du_titulaire(
            acteur.id, self._socle.horloge.maintenant(), pagination.page, pagination.taille)

    def rechercher(self, criteres: CriteresHistorique,
                   pagination: Pagination) -> tuple[Sequence[Reservation], int]:
        """A-08 : qui a réservé ou annulé, et quand (route réservée au
        gestionnaire)."""
        fuseau = self._socle.parametres.fuseau
        if criteres.du and criteres.au and criteres.au < criteres.du:
            raise DonneesInvalides("La date de fin précède la date de début.",
                                   code="periode_invalide")
        filtres = FiltresReservations(
            salle_id=criteres.salle_id,
            debut_min=bornes_journee(criteres.du, fuseau).debut if criteres.du else None,
            debut_max=bornes_journee(criteres.au, fuseau).fin if criteres.au else None,
            statut=criteres.statut,
            recherche=criteres.recherche,
        )
        return self._reservations.rechercher(filtres, pagination.page, pagination.taille)

    def de_la_periode(self, du: date, au: date) -> Sequence[Reservation]:
        """Réservations d'une période (bornes incluses) pour l'export CSV (A-10)."""
        reglages = self._socle.parametres
        if au < du:
            raise DonneesInvalides("La date de fin précède la date de début.",
                                   code="periode_invalide")
        if (au - du).days + 1 > reglages.export_periode_max_jours:
            raise DonneesInvalides(
                f"Période trop longue : {reglages.export_periode_max_jours} jours au maximum.",
                code="periode_trop_longue",
            )
        return self._reservations.sur_periode(bornes_journee(du, reglages.fuseau).debut,
                                              bornes_journee(au, reglages.fuseau).fin)
