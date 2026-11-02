"""Cas d'usage testés sans base ni serveur, grâce aux dépôts en mémoire
injectés (tests/unitaires/faux.py). Les tests d'accès de bout en bout, par
HTTP et avec PostgreSQL, sont dans tests/droits/."""
from datetime import date, time, timedelta

import pytest

from app.domaine.enums import EtatSalle, Role, StatutReservation
from app.domaine.erreurs import (
    AccesRefuse,
    AuthentificationRequise,
    Conflit,
    DonneesInvalides,
    RessourceIntrouvable,
    TropDeTentatives,
)
from app.services.auth import delai_apres_echecs
from app.services.fermetures import DemandeFermeture
from app.services.reservations import CriteresHistorique, DemandeReservation, Pagination
from app.services.salles import DonneesSalle, ModificationSalle

from .faux import LUNDI, a, application


@pytest.fixture
def appli():
    return application()


def demande(salle, debut: int, fin: int, jour=LUNDI) -> DemandeReservation:
    return DemandeReservation(salle.id, a(debut, jour), a(fin, jour), "**TP** réseaux")


# ------------------------------------------------------------ réserver


class TestReserver:
    def test_reservation_valide_puis_diffusee_apres_validation(self, appli):
        etudiant, salle = appli.personne(Role.ETUDIANT), appli.salle()
        reservation = appli.reservations.creer(etudiant, demande(salle, 10, 12))
        assert reservation.statut == StatutReservation.ACTIVE
        assert appli.transaction.validations == 1
        assert appli.journal.noms() == ["reservation.creee"]
        assert appli.diffusion.evenements == [
            {"type": "planning", "salle_id": str(salle.id), "jours": ["2026-11-02"]}]

    def test_creneau_deja_pris_refuse(self, appli):  # A-03
        salle = appli.salle()
        appli.reservations.creer(appli.personne(Role.ENSEIGNANT), demande(salle, 10, 12))
        with pytest.raises(Conflit) as erreur:
            appli.reservations.creer(appli.personne(Role.ETUDIANT), demande(salle, 11, 13))
        assert erreur.value.code == "creneau_deja_reserve"

    def test_creneaux_bout_a_bout_acceptes(self, appli):
        salle = appli.salle()
        appli.reservations.creer(appli.personne(Role.ENSEIGNANT), demande(salle, 10, 12))
        appli.reservations.creer(appli.personne(Role.ETUDIANT), demande(salle, 12, 13))

    def test_pas_deux_salles_en_meme_temps(self, appli):
        etudiant = appli.personne(Role.ETUDIANT)
        appli.reservations.creer(etudiant, demande(appli.salle("D101"), 10, 11))
        with pytest.raises(Conflit) as erreur:
            appli.reservations.creer(etudiant, demande(appli.salle("D102"), 10, 11))
        assert erreur.value.code == "reservation_simultanee"

    def test_etudiant_limite_a_deux_heures_d_affilee(self, appli):  # A-09
        etudiant, salle = appli.personne(Role.ETUDIANT), appli.salle()
        appli.reservations.creer(etudiant, demande(salle, 10, 12))
        with pytest.raises(AccesRefuse) as erreur:
            appli.reservations.creer(etudiant, demande(appli.salle("D102"), 12, 13))
        assert erreur.value.code == "limite_etudiant_depassee"

    def test_enseignant_sans_limite(self, appli):  # A-09
        enseignant, salle = appli.personne(Role.ENSEIGNANT), appli.salle()
        appli.reservations.creer(enseignant, demande(salle, 8, 12))
        appli.reservations.creer(enseignant, demande(salle, 12, 16))

    def test_le_gestionnaire_ne_reserve_pas(self, appli):
        with pytest.raises(AccesRefuse):
            appli.reservations.creer(appli.personne(Role.GESTIONNAIRE),
                                     demande(appli.salle(), 10, 11))

    def test_creneau_passe_refuse(self, appli):
        appli.horloge.avancer(hours=3)  # il est 11 h 30
        with pytest.raises(DonneesInvalides):
            appli.reservations.creer(appli.personne(Role.ETUDIANT), demande(appli.salle(), 10, 11))

    def test_salle_fermee_ou_retiree(self, appli):
        etudiant = appli.personne(Role.ETUDIANT)
        with pytest.raises(Conflit):
            appli.reservations.creer(etudiant, demande(appli.salle("F1", etat=EtatSalle.FERMEE),
                                                       10, 11))
        with pytest.raises(RessourceIntrouvable):
            appli.reservations.creer(etudiant, demande(appli.salle("R1", etat=EtatSalle.RETIREE),
                                                       10, 11))

    def test_creneau_ferme_par_le_gestionnaire(self, appli):  # A-07
        salle = appli.salle()
        appli.fermetures.fermer(appli.personne(Role.GESTIONNAIRE),
                                DemandeFermeture(salle.id, a(9), a(12), "Travaux"))
        with pytest.raises(Conflit) as erreur:
            appli.reservations.creer(appli.personne(Role.ETUDIANT), demande(salle, 10, 11))
        assert erreur.value.code == "creneau_ferme"

    def test_hors_des_horaires_de_la_salle(self, appli):
        salle = appli.salle(heure_ouverture=time(9), heure_fermeture=time(17))
        with pytest.raises(DonneesInvalides):
            appli.reservations.creer(appli.personne(Role.ENSEIGNANT), demande(salle, 16, 18))


# ------------------------------------------------------------- annuler


class TestAnnuler:
    def test_le_titulaire_annule_et_l_historique_reste(self, appli):  # A-05, A-08
        etudiant = appli.personne(Role.ETUDIANT)
        reservation = appli.reservations.creer(etudiant, demande(appli.salle(), 10, 11))
        appli.reservations.annuler(etudiant, reservation.id)
        assert reservation.statut == StatutReservation.ANNULEE
        assert reservation.annulee_par_id == etudiant.id
        assert reservation in appli.memoire.reservations  # jamais supprimée

    def test_un_autre_utilisateur_ne_peut_pas_annuler(self, appli):  # A-06
        reservation = appli.reservations.creer(appli.personne(Role.ETUDIANT),
                                               demande(appli.salle(), 10, 11))
        with pytest.raises(AccesRefuse):
            appli.reservations.annuler(appli.personne(Role.ENSEIGNANT), reservation.id)
        assert reservation.statut == StatutReservation.ACTIVE

    def test_le_gestionnaire_annule_celle_d_un_autre(self, appli):  # A-06
        reservation = appli.reservations.creer(appli.personne(Role.ETUDIANT),
                                               demande(appli.salle(), 10, 11))
        gestionnaire = appli.personne(Role.GESTIONNAIRE)
        appli.reservations.annuler(gestionnaire, reservation.id, "Examen")
        assert (reservation.annulee_par_id, reservation.motif_annulation) == \
            (gestionnaire.id, "Examen")

    def test_ni_deux_fois_ni_apres_coup(self, appli):
        etudiant = appli.personne(Role.ETUDIANT)
        reservation = appli.reservations.creer(etudiant, demande(appli.salle(), 10, 11))
        appli.horloge.avancer(hours=3)
        with pytest.raises(Conflit) as erreur:
            appli.reservations.annuler(etudiant, reservation.id)
        assert erreur.value.code == "reservation_terminee"


# ------------------------------------------------- consulter et exporter


def test_mes_reservations_paginees(appli):
    enseignant, salle = appli.personne(Role.ENSEIGNANT), appli.salle()
    for heure in range(9, 14):
        appli.reservations.creer(enseignant, demande(salle, heure, heure + 1))
    page, total = appli.reservations.a_venir(enseignant, Pagination(page=2, taille=2))
    assert total == 5
    assert [r.debut.hour for r in page] == [11, 12]
    assert appli.reservations.historique(enseignant, Pagination()) == ([], 0)


def test_planning_masque_les_details_aux_autres(appli):  # A-01
    etud, etud2 = appli.personne(Role.ETUDIANT), appli.personne(Role.ETUDIANT, "etud2")
    appli.reservations.creer(etud, demande(appli.salle(), 10, 11))
    vue_etud2 = appli.planning.du_jour(etud2, LUNDI.date())
    vue_gestionnaire = appli.planning.du_jour(appli.personne(Role.GESTIONNAIRE),
                                              LUNDI.date())
    assert [r.details_visibles for r in vue_etud2.reservations] == [False]
    assert [r.details_visibles for r in vue_gestionnaire.reservations] == [True]


def test_export_borne(appli):  # A-10
    with pytest.raises(DonneesInvalides) as erreur:
        appli.reservations.de_la_periode(date(2026, 1, 1), date(2027, 1, 2))
    assert erreur.value.code == "periode_trop_longue"
    with pytest.raises(DonneesInvalides):
        appli.reservations.rechercher(CriteresHistorique(du=date(2026, 2, 1),
                                                         au=date(2026, 1, 1)), Pagination())


# --------------------------------------------------- gestion des salles


class TestGestion:
    def test_fermer_un_creneau_annule_les_reservations_touchees(self, appli):  # A-07
        salle = appli.salle()
        reservation = appli.reservations.creer(appli.personne(Role.ETUDIANT),
                                               demande(salle, 10, 11))
        _, annulees = appli.fermetures.fermer(appli.personne(Role.GESTIONNAIRE),
                                              DemandeFermeture(salle.id, a(9), a(12), "Panne"))
        assert annulees == 1
        assert reservation.motif_annulation == "Créneau fermé : Panne"

    def test_seul_le_gestionnaire_ferme_ou_modifie(self, appli):
        etudiant, salle = appli.personne(Role.ETUDIANT), appli.salle()
        with pytest.raises(AccesRefuse):
            appli.fermetures.fermer(etudiant, DemandeFermeture(salle.id, a(9), a(12), "x"))
        with pytest.raises(AccesRefuse):
            appli.salles.modifier(etudiant, salle.id, ModificationSalle({"etat": EtatSalle.FERMEE}))
        with pytest.raises(AccesRefuse):
            appli.salles.lister_toutes(etudiant)

    def test_fermer_une_salle_annule_ses_reservations_a_venir(self, appli):
        salle = appli.salle()
        reservation = appli.reservations.creer(appli.personne(Role.ENSEIGNANT),
                                               demande(salle, 14, 16))
        _, annulees = appli.salles.modifier(appli.personne(Role.GESTIONNAIRE), salle.id,
                                            ModificationSalle({"etat": EtatSalle.FERMEE}))
        assert annulees == 1
        assert reservation.motif_annulation == "Salle fermée par le gestionnaire"
        assert appli.diffusion.evenements[-1] == {"type": "salles"}

    def test_reduire_les_horaires_annule_ce_qui_en_sort(self, appli):
        salle = appli.salle()
        enseignant = appli.personne(Role.ENSEIGNANT)
        dedans = appli.reservations.creer(enseignant, demande(salle, 10, 11))
        dehors = appli.reservations.creer(enseignant, demande(salle, 18, 19))
        appli.salles.modifier(appli.personne(Role.GESTIONNAIRE), salle.id,
                              ModificationSalle({"heure_fermeture": time(17)}))
        assert (dedans.statut, dehors.statut) == (StatutReservation.ACTIVE,
                                                  StatutReservation.ANNULEE)

    def test_seuls_les_champs_autorises_sont_modifies(self, appli):
        salle = appli.salle()
        appli.salles.modifier(appli.personne(Role.GESTIONNAIRE), salle.id,
                              ModificationSalle({"capacite": 40, "code": "PIRATE"}))
        assert (salle.capacite, salle.code) == (40, "D101")

    def test_code_de_salle_unique(self, appli):
        appli.salle("D101")
        with pytest.raises(Conflit):
            appli.salles.creer(appli.personne(Role.GESTIONNAIRE),
                               DonneesSalle(code="d101", batiment_id=appli.memoire.batiments[0].id,
                                            capacite=20))

    def test_changer_de_role_mais_pas_le_sien(self, appli):
        gestionnaire = appli.personne(Role.GESTIONNAIRE)
        etudiant = appli.personne(Role.ETUDIANT)
        appli.utilisateurs.changer_role(gestionnaire, etudiant.id, Role.ENSEIGNANT)
        assert etudiant.role == Role.ENSEIGNANT
        assert appli.journal_securite.noms() == ["utilisateur.role_modifie"]
        with pytest.raises(Conflit):
            appli.utilisateurs.changer_role(gestionnaire, gestionnaire.id, Role.ETUDIANT)
        with pytest.raises(AccesRefuse):
            appli.utilisateurs.changer_role(etudiant, gestionnaire.id, Role.ETUDIANT)


# ------------------------------------------------------ authentification


class TestAuthentification:
    def test_inscription_toujours_etudiant(self, appli):
        utilisateur = appli.auth.inscrire(" Etud2@IUT.fr ", "cheval batterie agrafe",
                                          "IUT", "Étudiant")
        assert (utilisateur.email, utilisateur.role) == ("etud2@iut.fr", Role.ETUDIANT)
        assert utilisateur.mot_de_passe != "cheval batterie agrafe"  # haché

    @pytest.mark.parametrize("mot_de_passe", ["motdepasse2026", "123456789012", "etud2-iut-2026"])
    def test_mot_de_passe_previsible_refuse(self, appli, mot_de_passe):
        with pytest.raises(DonneesInvalides) as erreur:
            appli.auth.inscrire("etud2@iut.fr", mot_de_passe, "IUT", "Étudiant")
        assert erreur.value.code == "mot_de_passe_previsible"

    def test_adresse_deja_utilisee(self, appli):
        appli.personne(Role.ETUDIANT)
        with pytest.raises(Conflit):
            appli.auth.inscrire("etud@iut.fr", "cheval batterie agrafe", "IUT", "Étudiant")

    def test_meme_erreur_pour_adresse_inconnue_et_mot_de_passe_faux(self, appli):
        appli.personne(Role.ETUDIANT)
        with pytest.raises(AuthentificationRequise) as inconnue:
            appli.auth.authentifier("personne@iut.fr", "x")
        with pytest.raises(AuthentificationRequise) as faux:
            appli.auth.authentifier("etud@iut.fr", "x")
        assert (inconnue.value.code, inconnue.value.message) == (faux.value.code,
                                                                 faux.value.message)

    def test_delai_double_apres_les_essais_libres(self, appli):
        appli.personne(Role.ETUDIANT)
        for _ in range(3):
            with pytest.raises(AuthentificationRequise):
                appli.auth.authentifier("etud@iut.fr", "mauvais")
        with pytest.raises(AuthentificationRequise):  # 4e échec : 1 s d'attente
            appli.auth.authentifier("etud@iut.fr", "mauvais")
        with pytest.raises(TropDeTentatives) as attente:  # même le bon mot de passe attend
            appli.auth.authentifier("etud@iut.fr", "motdepasse-correct")
        assert attente.value.reessayer_dans == 1
        appli.horloge.avancer(seconds=1)
        with pytest.raises(AuthentificationRequise):  # 5e échec : 2 s
            appli.auth.authentifier("etud@iut.fr", "mauvais")
        appli.horloge.avancer(seconds=2)
        assert appli.auth.authentifier("etud@iut.fr", "motdepasse-correct").prenom == "Étudiant"
        assert "etud@iut.fr" not in appli.memoire.verrous  # compteur remis à zéro

    def test_l_adresse_saisie_n_est_pas_journalisee(self, appli):
        with pytest.raises(AuthentificationRequise):
            appli.auth.authentifier("victime@iut.fr", "x")
        nom, champs = appli.journal_securite.evenements[-1]
        assert nom == "connexion.echec"
        assert "victime@iut.fr" not in repr(champs)

    def test_session_revoquee_ou_expiree(self, appli):
        session = appli.auth.ouvrir_session(appli.personne(Role.ETUDIANT))
        assert appli.auth.session_active(session.id)
        appli.auth.revoquer_session(session.id)
        assert not appli.auth.session_active(session.id)
        autre = appli.auth.ouvrir_session(appli.personne(Role.ETUDIANT, "etud2"))
        appli.horloge.avancer(hours=13)
        assert not appli.auth.session_active(autre.id)


def test_delai_apres_echecs():
    reglages = {"essais_libres": 3, "initial": timedelta(seconds=1),
                "maximum": timedelta(minutes=15)}
    assert [delai_apres_echecs(n, **reglages).total_seconds() for n in range(1, 8)] == \
        [0, 0, 0, 1, 2, 4, 8]
    assert delai_apres_echecs(1000, **reglages) == timedelta(minutes=15)
