"""Droits du gestionnaire : A-07 (salles, créneaux), A-08 (historique),
A-10 (export) et attribution des rôles."""
import pytest

from .conftest import creneau

pytestmark = pytest.mark.base

NON_GESTIONNAIRES = ["etudiant", "enseignant"]


@pytest.mark.parametrize("role", NON_GESTIONNAIRES)
def test_a07_seul_le_gestionnaire_cree_une_salle(connecte, jeu, role):
    corps = {"code": "Z999", "batiment_id": str(jeu.batiment), "capacite": 4}
    assert connecte(role).post("/api/salles", json=corps).status_code == 403
    assert connecte("gestionnaire").post("/api/salles", json=corps).status_code == 201


@pytest.mark.parametrize("etat", ["fermee", "retiree", "ouverte"])
@pytest.mark.parametrize("role", NON_GESTIONNAIRES)
def test_a07_seul_le_gestionnaire_ouvre_ferme_ou_retire(connecte, jeu, role, etat):
    reponse = connecte(role).patch(f"/api/salles/{jeu.salle}", json={"etat": etat})
    assert reponse.status_code == 403


def test_a07_fermer_une_salle_annule_ses_reservations(connecte, jeu):
    etud = connecte("etudiant")
    reservation_id = etud.reserver(jeu.salle, jeu.jour, 10, 12).get_json()["id"]

    reponse = connecte("gestionnaire").patch(f"/api/salles/{jeu.salle}", json={"etat": "fermee"})
    assert reponse.status_code == 200
    assert reponse.get_json()["reservations_annulees"] == 1

    historique = etud.get("/api/moi/reservations?periode=passees").get_json()["elements"]
    annulee = next(r for r in historique if r["id"] == reservation_id)
    assert annulee["statut"] == "annulee"
    assert annulee["motif_annulation"] == "Salle fermée par le gestionnaire"
    nouvelle = etud.reserver(jeu.salle, jeu.jour, 14, 15)
    assert nouvelle.status_code == 409
    assert nouvelle.get_json()["code"] == "salle_fermee"


def test_a07_une_salle_retiree_quitte_le_planning(connecte, jeu):
    gestionnaire = connecte("gestionnaire")
    gestionnaire.patch(f"/api/salles/{jeu.salle2}", json={"etat": "retiree"})
    planning = connecte("etudiant").get(f"/api/planning?date={jeu.jour.isoformat()}").get_json()
    assert [s["code"] for s in planning["salles"]] == ["D101"]


@pytest.mark.parametrize("role", NON_GESTIONNAIRES)
def test_a07_seul_le_gestionnaire_ferme_un_creneau(connecte, jeu, role):
    corps = {"salle_id": str(jeu.salle), **creneau(jeu.jour, 8, 12), "motif": "Travaux"}
    assert connecte(role).post("/api/fermetures", json=corps).status_code == 403


def test_a07_creneau_ferme_puis_rouvert(connecte, jeu):
    gestionnaire = connecte("gestionnaire")
    corps = {"salle_id": str(jeu.salle), **creneau(jeu.jour, 8, 12), "motif": "Travaux"}
    fermeture = gestionnaire.post("/api/fermetures", json=corps)
    assert fermeture.status_code == 201
    fermeture_id = fermeture.get_json()["id"]

    etud = connecte("etudiant")
    refus = etud.reserver(jeu.salle, jeu.jour, 9, 10)
    assert refus.status_code == 409
    assert refus.get_json()["code"] == "creneau_ferme"

    assert etud.delete(f"/api/fermetures/{fermeture_id}").status_code == 403
    assert gestionnaire.delete(f"/api/fermetures/{fermeture_id}").status_code == 204
    assert etud.reserver(jeu.salle, jeu.jour, 9, 10).status_code == 201


@pytest.mark.parametrize("role", NON_GESTIONNAIRES)
def test_a08_historique_reserve_au_gestionnaire(connecte, jeu, role):
    assert connecte(role).get("/api/reservations").status_code == 403


def test_a08_le_gestionnaire_retrouve_qui_a_reserve_et_annule(connecte, jeu):
    etud = connecte("etudiant")
    reservation_id = etud.reserver(jeu.salle, jeu.jour, 10, 12).get_json()["id"]
    etud.patch(f"/api/reservations/{reservation_id}", json={"statut": "annulee"})

    jour = jeu.jour.isoformat()
    page = connecte("gestionnaire").get(
        f"/api/reservations?salle_id={jeu.salle}&du={jour}&au={jour}").get_json()
    assert page["total"] == 1
    ligne = page["elements"][0]
    assert ligne["titulaire"]["email"] == "etud@iut.fr"
    assert ligne["cree_le"]
    assert ligne["annulee_par"]["email"] == "etud@iut.fr"
    assert ligne["annulee_le"]


@pytest.mark.parametrize("role", NON_GESTIONNAIRES)
def test_a10_export_reserve_au_gestionnaire(connecte, jeu, role):
    jour = jeu.jour.isoformat()
    assert connecte(role).get(f"/api/reservations/export?du={jour}&au={jour}").status_code == 403


def test_a10_export_csv(connecte, jeu):
    connecte("etudiant").reserver(jeu.salle, jeu.jour, 10, 12, "=CMD|' /C calc'!A0")
    jour = jeu.jour.isoformat()
    reponse = connecte("gestionnaire").get(f"/api/reservations/export?du={jour}&au={jour}")
    assert reponse.status_code == 200
    assert reponse.mimetype == "text/csv"
    contenu = reponse.get_data(as_text=True)
    assert "D101" in contenu
    assert "'=CMD" in contenu  # formule neutralisée


@pytest.mark.parametrize("role", NON_GESTIONNAIRES)
def test_salles_retirees_visibles_du_seul_gestionnaire(connecte, jeu, role):
    assert connecte(role).get("/api/salles?inclure_retirees=true").status_code == 403
    assert connecte("gestionnaire").get("/api/salles?inclure_retirees=true").status_code == 200


@pytest.mark.parametrize("role", NON_GESTIONNAIRES)
def test_seul_le_gestionnaire_attribue_les_roles(connecte, jeu, role):
    client = connecte(role)
    assert client.get("/api/utilisateurs").status_code == 403
    reponse = client.patch(f"/api/utilisateurs/{jeu.etudiant}", json={"role": "gestionnaire"})
    assert reponse.status_code == 403


def test_le_gestionnaire_ne_change_pas_son_propre_role(connecte, jeu):
    reponse = connecte("gestionnaire").patch(f"/api/utilisateurs/{jeu.gestionnaire}",
                                             json={"role": "etudiant"})
    assert reponse.status_code == 409


def test_un_changement_de_role_s_applique_immediatement(connecte, jeu):
    etud2 = connecte("etudiant2")
    assert etud2.reserver(jeu.salle, jeu.jour, 8, 11).status_code == 403
    connecte("gestionnaire").patch(f"/api/utilisateurs/{jeu.etudiant2}",
                                   json={"role": "enseignant"})
    # Même session, même jeton : le rôle est relu en base à chaque requête.
    assert etud2.reserver(jeu.salle, jeu.jour, 8, 11).status_code == 201
