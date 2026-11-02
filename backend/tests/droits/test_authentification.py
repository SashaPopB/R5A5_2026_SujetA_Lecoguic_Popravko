"""Authentification : sans session valide, rien n'est accessible."""
import re
import uuid

import pytest

from .conftest import EMAILS, MOT_DE_PASSE, creneau

pytestmark = pytest.mark.base

UN_ID = str(uuid.uuid4())

ROUTES_PROTEGEES = [
    ("get", "/api/auth/moi"),
    ("get", "/api/planning"),
    ("get", "/api/batiments"),
    ("get", "/api/salles"),
    ("get", "/api/moi/reservations"),
    ("get", "/api/reservations"),
    ("get", "/api/reservations/export?du=2026-01-01&au=2026-01-31"),
    ("post", "/api/reservations"),
    ("patch", f"/api/reservations/{UN_ID}"),
    ("post", "/api/salles"),
    ("patch", f"/api/salles/{UN_ID}"),
    ("post", "/api/fermetures"),
    ("delete", f"/api/fermetures/{UN_ID}"),
    ("get", "/api/utilisateurs"),
    ("patch", f"/api/utilisateurs/{UN_ID}"),
    ("get", "/api/evenements"),
]


@pytest.mark.parametrize("methode,url", ROUTES_PROTEGEES)
def test_sans_session_tout_est_refuse(anonyme, jeu, methode, url):
    corps = {} if methode in {"post", "patch"} else None
    reponse = getattr(anonyme.client, methode)(url, json=corps)
    assert reponse.status_code == 401


# Seules exceptions au refus par défaut (@route_publique). Ajouter une route
# publique oblige à la déclarer ici : c'est une décision, pas un oubli.
ROUTES_PUBLIQUES = {
    "auth.inscription", "auth.connexion", "auth.rafraichissement", "auth.deconnexion",
    "systeme.sante", "documentation.document_openapi", "documentation.swagger_ui",
    "documentation.swagger_initialisation",
}


def _url_exemple(regle) -> str:
    """Remplace chaque paramètre de la route par une valeur bien formée."""
    url = regle.rule
    for nom in regle.arguments:
        url = re.sub(rf"<(?:[a-z]+:)?{nom}>", UN_ID, url)
    return url


def test_toute_route_non_publique_refuse_sans_session(app, anonyme, jeu):
    """Parcourt TOUTES les routes déclarées : une route ajoutée plus tard sans
    protection ferait échouer ce test."""
    from app.api.openapi import est_publique

    publiques, verifiees = set(), 0
    for regle in app.url_map.iter_rules():
        if regle.endpoint == "static":
            continue
        if est_publique(app.view_functions[regle.endpoint]):
            publiques.add(regle.endpoint)
            continue
        for methode in sorted(regle.methods - {"HEAD", "OPTIONS"}):
            corps = {} if methode in {"POST", "PUT", "PATCH"} else None
            reponse = anonyme.client.open(_url_exemple(regle), method=methode, json=corps)
            assert reponse.status_code == 401, f"{methode} {regle.rule} accessible sans session"
            verifiees += 1
    assert publiques == ROUTES_PUBLIQUES
    assert verifiees >= len(ROUTES_PROTEGEES)


def test_routes_publiques(anonyme, jeu):
    assert anonyme.get("/api/sante").status_code == 200
    assert anonyme.get("/api/openapi.json").status_code == 200


def test_modification_sans_jeton_csrf_refusee(connecte, jeu):
    """Le cookie seul ne suffit pas : un site tiers ne peut pas lire le jeton
    CSRF, donc ne peut pas forger une requête au nom de l'utilisateur."""
    etudiant = connecte("etudiant")
    corps = {"salle_id": str(jeu.salle), **creneau(jeu.jour, 10, 11), "description": "test"}
    sans_jeton = etudiant.post("/api/reservations", json=corps, csrf=False)
    assert sans_jeton.status_code == 401
    assert sans_jeton.get_json()["code"] == "csrf_invalide"
    faux_jeton = etudiant.client.post("/api/reservations", json=corps,
                                      headers={"X-CSRF-TOKEN": "faux"})
    assert faux_jeton.status_code == 401
    assert etudiant.post("/api/reservations", json=corps).status_code == 201


def test_deconnexion_revoque_le_jeton_d_acces(app, connecte, jeu):
    etudiant = connecte("etudiant")
    jeton_vole = etudiant.cookie("access_token_cookie")
    assert jeton_vole
    reponse = etudiant.post("/api/auth/deconnexion", cookie_csrf="csrf_refresh_token")
    assert reponse.status_code == 204

    attaquant = app.test_client()
    attaquant.set_cookie("access_token_cookie", jeton_vole, path="/api/")
    reponse = attaquant.get("/api/auth/moi")
    assert reponse.status_code == 401
    assert reponse.get_json()["code"] == "session_revoquee"


def test_deconnexion_revoque_le_jeton_de_rafraichissement(app, connecte, jeu):
    etudiant = connecte("etudiant")
    jeton = etudiant.cookie("refresh_token_cookie")
    csrf = etudiant.cookie("csrf_refresh_token")
    assert jeton and csrf
    deconnexion = etudiant.post("/api/auth/deconnexion", cookie_csrf="csrf_refresh_token")
    assert deconnexion.status_code == 204

    attaquant = app.test_client()
    attaquant.set_cookie("refresh_token_cookie", jeton, path="/api/auth/")
    reponse = attaquant.post("/api/auth/rafraichissement", headers={"X-CSRF-TOKEN": csrf})
    assert reponse.status_code == 401


def test_rafraichissement_prolonge_une_session_valide(connecte, jeu):
    etudiant = connecte("etudiant")
    reponse = etudiant.post("/api/auth/rafraichissement", cookie_csrf="csrf_refresh_token")
    assert reponse.status_code == 204
    assert etudiant.get("/api/auth/moi").status_code == 200


def test_inscription_ne_permet_pas_de_choisir_son_role(anonyme, jeu):
    corps = {"email": "etud3@iut.fr", "mot_de_passe": "un-mot-de-passe-long",
             "nom": "IUT", "prenom": "Étudiant"}
    tentative = anonyme.post("/api/auth/inscription", json={**corps, "role": "gestionnaire"},
                             csrf=False)
    assert tentative.status_code == 400

    reponse = anonyme.post("/api/auth/inscription", json=corps, csrf=False)
    assert reponse.status_code == 201
    assert reponse.get_json()["role"] == "etudiant"
    assert anonyme.get("/api/reservations").status_code == 403


def test_force_brute_ralentie(anonyme, jeu):
    # Trois essais libres, puis un délai croissant (30 s pour le premier en
    # configuration de test, pour ne pas dépendre de la vitesse de la machine).
    for _ in range(4):
        assert anonyme.connexion(EMAILS["etudiant"], "mauvais-mot-de-passe").status_code == 401
    # Pendant le délai, même le bon mot de passe doit attendre.
    reponse = anonyme.connexion(EMAILS["etudiant"], MOT_DE_PASSE)
    assert reponse.status_code == 429
    assert int(reponse.headers["Retry-After"]) > 0
    # Le délai porte sur l'adresse visée, pas sur les autres comptes.
    assert anonyme.connexion(EMAILS["enseignant"], MOT_DE_PASSE).status_code == 200


def test_adresse_inconnue_indiscernable(anonyme, jeu):
    inconnue = anonyme.connexion("personne@iut.fr", "x")
    existante = anonyme.connexion(EMAILS["etudiant"], "x")
    assert inconnue.status_code == existante.status_code == 401
    assert inconnue.get_json() == existante.get_json()


def test_flux_temps_reel_ouvert_aux_connectes(connecte, jeu):
    etudiant = connecte("etudiant")
    reponse = etudiant.client.get("/api/evenements", buffered=False)
    try:
        assert reponse.status_code == 200
        assert reponse.mimetype == "text/event-stream"
        assert next(iter(reponse.response)).startswith(b"retry:")
    finally:
        reponse.close()
