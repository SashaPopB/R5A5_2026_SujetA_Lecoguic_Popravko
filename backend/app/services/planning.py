"""Vue « planning » d'une journée (A-01, A-03)."""
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from ..domaine.creneaux import bornes_journee
from ..domaine.enums import Role
from .contexte import ParametresMetier
from .ports import (
    DepotFermetures,
    DepotReservations,
    DepotSalles,
    Fermeture,
    Reservation,
    Salle,
    Utilisateur,
)


@dataclass(frozen=True)
class ReservationVue:
    reservation: Reservation
    est_a_moi: bool
    details_visibles: bool


@dataclass(frozen=True)
class Planning:
    jour: date
    jour_ouvert: bool
    salles: Sequence[Salle]
    reservations: list[ReservationVue]
    fermetures: list[Fermeture]


def peut_voir_details(acteur: Utilisateur, reservation: Reservation) -> bool:
    """Minimisation des données : tout le monde voit qu'un créneau est pris,
    seuls le titulaire et le gestionnaire voient qui l'a pris et pourquoi
    (la description peut contenir des liens privés)."""
    return reservation.utilisateur_id == acteur.id or acteur.role == Role.GESTIONNAIRE


class ServicePlanning:
    def __init__(self, parametres: ParametresMetier, *, salles: DepotSalles,
                 reservations: DepotReservations, fermetures: DepotFermetures) -> None:
        self._parametres = parametres
        self._salles = salles
        self._reservations = reservations
        self._fermetures = fermetures

    def du_jour(self, acteur: Utilisateur, jour: date) -> Planning:
        journee = bornes_journee(jour, self._parametres.fuseau)
        salles = self._salles.lister_proposees()
        ids_salles = {salle.id for salle in salles}
        reservations = self._reservations.actives_chevauchant(journee.debut, journee.fin)
        fermetures = self._fermetures.chevauchant(journee.debut, journee.fin)
        return Planning(
            jour=jour,
            jour_ouvert=jour.weekday() in self._parametres.jours_ouverture,
            salles=salles,
            reservations=[
                ReservationVue(r, r.utilisateur_id == acteur.id, peut_voir_details(acteur, r))
                for r in reservations if r.salle_id in ids_salles
            ],
            fermetures=[f for f in fermetures if f.salle_id in ids_salles],
        )
