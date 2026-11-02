"""Règles horaires du domaine, en fonctions pures (testables sans base).

Le planning est une grille horaire : une réservation ou une fermeture
commence et finit à une heure pleine, dans le fuseau de l'IUT.
"""
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .erreurs import AccesRefuse, DonneesInvalides


@dataclass(frozen=True)
class Intervalle:
    """Plage [debut, fin[ (la fin est exclue, comme tstzrange '[)')."""

    debut: datetime
    fin: datetime

    @property
    def duree(self) -> timedelta:
        # Conversion en UTC indispensable : entre deux dates du même fuseau,
        # Python soustrait les heures « murales » et ignorerait le passage à
        # l'heure d'hiver ou d'été.
        return self.fin.astimezone(UTC) - self.debut.astimezone(UTC)


def en_heure_locale(instant: datetime, fuseau: ZoneInfo) -> datetime:
    """Une date sans fuseau est interprétée comme une heure de l'IUT."""
    if instant.tzinfo is None:
        return instant.replace(tzinfo=fuseau)
    return instant.astimezone(fuseau)


def debut_heure_courante(maintenant: datetime) -> datetime:
    return maintenant.replace(minute=0, second=0, microsecond=0)


def bornes_journee(jour: date, fuseau: ZoneInfo) -> Intervalle:
    """Minuit à minuit, heure locale (gère les changements d'heure)."""
    return Intervalle(
        datetime.combine(jour, time.min, tzinfo=fuseau),
        datetime.combine(jour + timedelta(days=1), time.min, tzinfo=fuseau),
    )


def construire_plage(debut: datetime, fin: datetime, fuseau: ZoneInfo) -> Intervalle:
    """Valide une plage saisie : heures pleines, fin après début. Une plage
    peut couvrir plusieurs jours (fermeture d'une salle pour une semaine)."""
    debut = en_heure_locale(debut, fuseau)
    fin = en_heure_locale(fin, fuseau)
    for libelle, instant in (("début", debut), ("fin", fin)):
        if (instant.minute, instant.second, instant.microsecond) != (0, 0, 0):
            raise DonneesInvalides(
                f"L'heure de {libelle} doit être une heure pleine (ex. 14:00).",
                code="heure_non_pleine",
            )
    if fin <= debut:
        raise DonneesInvalides("La fin doit être postérieure au début.", code="plage_vide")
    return Intervalle(debut, fin)


def construire_creneau(debut: datetime, fin: datetime, fuseau: ZoneInfo) -> Intervalle:
    """Créneau de réservation : une plage valide qui tient sur une journée."""
    plage = construire_plage(debut, fin, fuseau)
    if plage.fin.date() != plage.debut.date():
        raise DonneesInvalides("Une réservation tient sur une seule journée.",
                               code="plage_sur_plusieurs_jours")
    return plage


def verifier_non_passe(plage: Intervalle, maintenant: datetime) -> None:
    """Le créneau de l'heure en cours reste réservable, pas les précédents."""
    if plage.debut < debut_heure_courante(maintenant):
        raise DonneesInvalides("Ce créneau est déjà passé.", code="creneau_passe")


def verifier_horizon(plage: Intervalle, maintenant: datetime, horizon_jours: int) -> None:
    if plage.debut > maintenant + timedelta(days=horizon_jours):
        raise DonneesInvalides(
            f"On ne réserve pas plus de {horizon_jours} jours à l'avance.",
            code="hors_horizon",
        )


def verifier_jour_ouvert(jour: date, jours_ouverture: Collection[int]) -> None:
    if jour.weekday() not in jours_ouverture:
        raise DonneesInvalides("L'IUT est fermé ce jour-là.", code="jour_ferme")


def verifier_horaires_salle(plage: Intervalle, ouverture: time, fermeture: time) -> None:
    # Une fin à minuit appartient au lendemain : elle est forcément hors horaires.
    fin_a_minuit = plage.fin.time() == time.min
    if plage.debut.time() < ouverture or plage.fin.time() > fermeture or fin_a_minuit:
        raise DonneesInvalides(
            f"La salle est ouverte de {ouverture:%H:%M} à {fermeture:%H:%M}.",
            code="hors_horaires_salle",
        )


def verifier_horaires_coherents(ouverture: time, fermeture: time) -> None:
    """Mêmes règles que la contrainte salle_horaires_coherents du schéma."""
    for valeur in (ouverture, fermeture):
        if (valeur.minute, valeur.second) != (0, 0):
            raise DonneesInvalides("Les horaires d'ouverture sont des heures pleines.",
                                   code="heure_non_pleine")
    if not time(6) <= ouverture < fermeture <= time(23):
        raise DonneesInvalides(
            "Horaires invalides : ouverture avant fermeture, entre 06:00 et 23:00.",
            code="horaires_invalides",
        )


def bloc_contigu(nouvelle: Intervalle, existantes: Iterable[Intervalle]) -> Intervalle:
    """Plage continue formée par la nouvelle réservation et celles qui la
    touchent ou la chevauchent, de proche en proche.

    Exemple : 10h-12h existante + nouvelle 12h-13h -> bloc 10h-13h.
    Tri puis fusion en un passage : O(n log n) pour n réservations du jour.
    """
    blocs: list[Intervalle] = []
    for plage in sorted([*existantes, nouvelle], key=lambda p: (p.debut, p.fin)):
        if blocs and plage.debut <= blocs[-1].fin:
            dernier = blocs[-1]
            blocs[-1] = Intervalle(dernier.debut, max(dernier.fin, plage.fin))
        else:
            blocs.append(plage)
    return next(b for b in blocs if b.debut <= nouvelle.debut and nouvelle.fin <= b.fin)


def verifier_limite_etudiant(nouvelle: Intervalle, reservations_du_jour: Iterable[Intervalle],
                             duree_max: timedelta) -> None:
    """A-09 : un étudiant ne réserve pas plus de `duree_max` d'affilée.

    On cumule les réservations collées les unes aux autres (dans n'importe
    quelle salle) : enchaîner 10h-12h puis 12h-13h revient à 3 h d'affilée.
    """
    bloc = bloc_contigu(nouvelle, reservations_du_jour)
    if bloc.duree > duree_max:
        heures = int(duree_max.total_seconds() // 3600)
        raise AccesRefuse(
            f"Un étudiant ne peut pas réserver plus de {heures} heures d'affilée "
            f"(cette réservation formerait un bloc de {bloc.debut:%H:%M} à {bloc.fin:%H:%M}).",
            code="limite_etudiant_depassee",
        )
