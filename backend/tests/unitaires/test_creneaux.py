"""Règles horaires pures (sans base de données)."""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.domaine.creneaux import (
    Intervalle,
    bloc_contigu,
    bornes_journee,
    construire_creneau,
    construire_plage,
    verifier_horaires_coherents,
    verifier_horaires_salle,
    verifier_jour_ouvert,
    verifier_limite_etudiant,
    verifier_non_passe,
)
from app.domaine.erreurs import AccesRefuse, DonneesInvalides

PARIS = ZoneInfo("Europe/Paris")
JOUR = date(2026, 11, 2)  # un lundi
DEUX_HEURES = timedelta(hours=2)


def h(heure: int, jour: date = JOUR) -> datetime:
    return datetime.combine(jour, time(heure), tzinfo=PARIS)


def plage(debut: int, fin: int) -> Intervalle:
    return Intervalle(h(debut), h(fin))


class TestConstruirePlage:
    def test_heure_sans_fuseau_interpretee_a_paris(self):
        resultat = construire_plage(datetime(2026, 11, 2, 10), datetime(2026, 11, 2, 12), PARIS)
        assert resultat.debut == h(10)
        assert resultat.debut.utcoffset() == timedelta(hours=1)

    def test_heure_avec_autre_fuseau_convertie(self):
        debut = datetime(2026, 11, 2, 9, tzinfo=ZoneInfo("UTC"))  # = 10h à Paris
        resultat = construire_plage(debut, debut + timedelta(hours=1), PARIS)
        assert resultat.debut.hour == 10

    @pytest.mark.parametrize("debut,fin", [
        (datetime(2026, 11, 2, 10, 30), datetime(2026, 11, 2, 12)),
        (datetime(2026, 11, 2, 10), datetime(2026, 11, 2, 11, 15)),
    ])
    def test_refuse_les_heures_non_pleines(self, debut, fin):
        with pytest.raises(DonneesInvalides) as erreur:
            construire_plage(debut, fin, PARIS)
        assert erreur.value.code == "heure_non_pleine"

    def test_refuse_une_plage_vide_ou_inversee(self):
        with pytest.raises(DonneesInvalides):
            construire_plage(h(12), h(10), PARIS)
        with pytest.raises(DonneesInvalides):
            construire_plage(h(12), h(12), PARIS)

    def test_refuse_plusieurs_jours_pour_une_reservation(self):
        with pytest.raises(DonneesInvalides) as erreur:
            construire_creneau(h(18), h(9, JOUR + timedelta(days=1)), PARIS)
        assert erreur.value.code == "plage_sur_plusieurs_jours"

    def test_accepte_plusieurs_jours_pour_une_fermeture(self):
        resultat = construire_plage(h(8), h(20, JOUR + timedelta(days=4)), PARIS)
        assert resultat.duree == timedelta(days=4, hours=12)


class TestBlocContigu:
    def test_reservation_isolee(self):
        assert bloc_contigu(plage(10, 12), []) == plage(10, 12)

    def test_fusion_avec_une_reservation_collee_avant(self):
        assert bloc_contigu(plage(12, 13), [plage(10, 12)]) == plage(10, 13)

    def test_fusion_de_proche_en_proche(self):
        assert bloc_contigu(plage(11, 12), [plage(9, 10), plage(10, 11), plage(12, 13)]) \
            == plage(9, 13)

    def test_un_trou_coupe_le_bloc(self):
        assert bloc_contigu(plage(13, 14), [plage(10, 12)]) == plage(13, 14)


class TestLimiteEtudiant:
    """A-09 : pas plus de deux heures d'affilée pour un étudiant."""

    def test_deux_heures_autorisees(self):
        verifier_limite_etudiant(plage(10, 12), [], DEUX_HEURES)

    def test_trois_heures_d_un_coup_refusees(self):
        with pytest.raises(AccesRefuse) as erreur:
            verifier_limite_etudiant(plage(10, 13), [], DEUX_HEURES)
        assert erreur.value.code == "limite_etudiant_depassee"

    def test_enchainement_qui_depasse_refuse(self):
        with pytest.raises(AccesRefuse):
            verifier_limite_etudiant(plage(12, 13), [plage(10, 12)], DEUX_HEURES)

    def test_enchainement_avant_qui_depasse_refuse(self):
        with pytest.raises(AccesRefuse):
            verifier_limite_etudiant(plage(9, 10), [plage(10, 12)], DEUX_HEURES)

    def test_une_pause_d_une_heure_suffit(self):
        verifier_limite_etudiant(plage(13, 15), [plage(10, 12)], DEUX_HEURES)


class TestAutresRegles:
    def test_l_heure_en_cours_reste_reservable(self):
        maintenant = h(10) + timedelta(minutes=40)
        verifier_non_passe(plage(10, 11), maintenant)

    def test_une_heure_terminee_ne_l_est_plus(self):
        maintenant = h(11) + timedelta(minutes=5)
        with pytest.raises(DonneesInvalides) as erreur:
            verifier_non_passe(plage(10, 11), maintenant)
        assert erreur.value.code == "creneau_passe"

    def test_jour_ferme(self):
        with pytest.raises(DonneesInvalides):
            verifier_jour_ouvert(date(2026, 11, 7), {0, 1, 2, 3, 4})  # samedi
        verifier_jour_ouvert(JOUR, {0, 1, 2, 3, 4})

    def test_horaires_de_la_salle(self):
        verifier_horaires_salle(plage(8, 10), time(8), time(20))
        with pytest.raises(DonneesInvalides):
            verifier_horaires_salle(plage(7, 9), time(8), time(20))
        with pytest.raises(DonneesInvalides):
            verifier_horaires_salle(plage(19, 21), time(8), time(20))

    @pytest.mark.parametrize("ouverture,fermeture", [
        (time(8, 30), time(20)), (time(20), time(8)), (time(5), time(12)), (time(8), time(23, 30)),
    ])
    def test_horaires_incoherents(self, ouverture, fermeture):
        with pytest.raises(DonneesInvalides):
            verifier_horaires_coherents(ouverture, fermeture)

    def test_bornes_d_une_journee_de_changement_d_heure(self):
        journee = bornes_journee(date(2026, 10, 25), PARIS)  # passage à l'heure d'hiver
        assert journee.duree == timedelta(hours=25)
