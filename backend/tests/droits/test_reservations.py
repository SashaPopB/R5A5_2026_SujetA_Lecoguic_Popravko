"""Droits sur les réservations : A-03, A-05, A-06, A-09 et visibilité."""
import pytest

pytestmark = pytest.mark.base


def _reservation_d_etud(connecte, jeu, debut=10, fin=12):
    etud = connecte("etudiant")
    reponse = etud.reserver(jeu.salle, jeu.jour, debut, fin)
    assert reponse.status_code == 201, reponse.get_json()
    return etud, reponse.get_json()["id"]


def test_a02_a03_creneau_pris_n_est_plus_reservable(connecte, jeu):
    etud = connecte("etudiant")
    reponse = etud.reserver(jeu.salle, jeu.jour, 10, 12,
                            "**Projet SAE**\n- maquettes\n[doc](https://exemple.org/doc)")
    assert reponse.status_code == 201
    assert reponse.get_json()["description"].startswith("**Projet SAE**")

    etud2 = connecte("etudiant2")
    conflit = etud2.reserver(jeu.salle, jeu.jour, 11, 12)
    assert conflit.status_code == 409
    assert conflit.get_json()["code"] == "creneau_deja_reserve"


def test_a02_lien_dangereux_refuse(connecte, jeu):
    etud = connecte("etudiant")
    reponse = etud.reserver(jeu.salle, jeu.jour, 10, 11, "[clic](javascript:alert(1))")
    assert reponse.status_code == 400
    assert reponse.get_json()["code"] == "lien_non_autorise"


@pytest.mark.parametrize("role", ["etudiant2", "enseignant"])
def test_a05_on_ne_peut_pas_annuler_la_reservation_d_un_autre(connecte, jeu, role):
    etud, reservation_id = _reservation_d_etud(connecte, jeu)
    autre = connecte(role)
    reponse = autre.patch(f"/api/reservations/{reservation_id}", json={"statut": "annulee"})
    assert reponse.status_code == 403
    a_venir = etud.get("/api/moi/reservations").get_json()["elements"]
    assert [r["id"] for r in a_venir] == [reservation_id]  # toujours active


def test_a05_le_titulaire_annule_la_sienne(connecte, jeu):
    etud, reservation_id = _reservation_d_etud(connecte, jeu)
    reponse = etud.patch(f"/api/reservations/{reservation_id}", json={"statut": "annulee"})
    assert reponse.status_code == 200
    donnees = reponse.get_json()
    assert donnees["statut"] == "annulee"
    assert donnees["annulee_par"]["id"] == str(jeu.etudiant)
    # L'annulation libère le créneau.
    assert connecte("etudiant2").reserver(jeu.salle, jeu.jour, 10, 12).status_code == 201


def test_a06_le_gestionnaire_annule_celle_d_un_autre(connecte, jeu):
    _, reservation_id = _reservation_d_etud(connecte, jeu)
    gestionnaire = connecte("gestionnaire")
    reponse = gestionnaire.patch(f"/api/reservations/{reservation_id}",
                                 json={"statut": "annulee", "motif": "Salle réquisitionnée"})
    assert reponse.status_code == 200
    assert reponse.get_json()["annulee_par"]["id"] == str(jeu.gestionnaire)
    assert reponse.get_json()["motif_annulation"] == "Salle réquisitionnée"


def test_une_reservation_annulee_ne_se_reactive_pas(connecte, jeu):
    etud, reservation_id = _reservation_d_etud(connecte, jeu)
    etud.patch(f"/api/reservations/{reservation_id}", json={"statut": "annulee"})
    deuxieme = etud.patch(f"/api/reservations/{reservation_id}", json={"statut": "annulee"})
    assert deuxieme.status_code == 409
    reactivation = etud.patch(f"/api/reservations/{reservation_id}", json={"statut": "active"})
    assert reactivation.status_code == 400


def test_a09_un_etudiant_ne_reserve_pas_plus_de_deux_heures(connecte, jeu):
    reponse = connecte("etudiant").reserver(jeu.salle, jeu.jour, 10, 13)
    assert reponse.status_code == 403
    assert reponse.get_json()["code"] == "limite_etudiant_depassee"


def test_a09_un_etudiant_ne_contourne_pas_la_limite_en_enchainant(connecte, jeu):
    etud = connecte("etudiant")
    assert etud.reserver(jeu.salle, jeu.jour, 10, 12).status_code == 201
    reponse = etud.reserver(jeu.salle2, jeu.jour, 12, 13)
    assert reponse.status_code == 403


def test_a09_l_enseignant_n_est_pas_limite(connecte, jeu):
    assert connecte("enseignant").reserver(jeu.salle, jeu.jour, 8, 12).status_code == 201


def test_on_n_occupe_pas_deux_salles_a_la_fois(connecte, jeu):
    enseignant = connecte("enseignant")
    assert enseignant.reserver(jeu.salle, jeu.jour, 8, 12).status_code == 201
    reponse = enseignant.reserver(jeu.salle2, jeu.jour, 10, 11)
    assert reponse.status_code == 409
    assert reponse.get_json()["code"] == "reservation_simultanee"


def test_le_gestionnaire_ne_reserve_pas(connecte, jeu):
    reponse = connecte("gestionnaire").reserver(jeu.salle, jeu.jour, 10, 11)
    assert reponse.status_code == 403


def test_planning_masque_qui_et_pourquoi_aux_autres(connecte, jeu):
    etud, _ = _reservation_d_etud(connecte, jeu)
    url = f"/api/planning?date={jeu.jour.isoformat()}"

    vue_d_etud2 = connecte("etudiant2").get(url).get_json()["reservations"][0]
    assert vue_d_etud2["est_a_moi"] is False
    assert vue_d_etud2["titulaire"] is None
    assert vue_d_etud2["description"] is None

    vue_d_etud = etud.get(url).get_json()["reservations"][0]
    assert vue_d_etud["est_a_moi"] is True
    assert vue_d_etud["description"] == "Travail de groupe"

    vue_du_gestionnaire = connecte("gestionnaire").get(url).get_json()["reservations"][0]
    assert vue_du_gestionnaire["titulaire"]["email"] == "etud@iut.fr"


def test_a04_une_reservation_est_diffusee_en_temps_reel(connecte, jeu):
    from app.extensions import diffuseur

    etud = connecte("etudiant")
    abonnement = diffuseur.abonner()
    try:
        assert etud.reserver(jeu.salle, jeu.jour, 10, 11).status_code == 201
        message = abonnement.file.get(timeout=2)
        assert jeu.jour.isoformat() in message
        assert message.startswith("id: ")  # rejouable après une coupure (Last-Event-ID)
        assert "etud" not in message  # aucune donnée personnelle dans le flux
    finally:
        diffuseur.desabonner(abonnement.file)


def test_mes_reservations_ne_montrent_que_les_miennes(connecte, jeu):
    _reservation_d_etud(connecte, jeu)
    assert connecte("etudiant2").get("/api/moi/reservations").get_json()["elements"] == []
