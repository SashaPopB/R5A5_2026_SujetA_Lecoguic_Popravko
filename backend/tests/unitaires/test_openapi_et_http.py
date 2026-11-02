"""Génération OpenAPI, en-têtes de sécurité et journal des requêtes, testés
sur une petite application Flask (sans base de données)."""
import json
import logging

import pytest
from flask import Blueprint, Flask, Response, jsonify

from app.api import dto
from app.api.openapi import documenter, generer_openapi, route_publique
from app.journalisation import FormateurJson, configurer_journalisation
from app.securite_http import configurer_securite_http, origine_acceptee


@pytest.fixture
def appli() -> Flask:
    app = Flask(__name__)
    app.config.update(HSTS_ACTIF=True, LOG_LEVEL="INFO", LOG_DIR="",
                      LOG_RETENTION_JOURS=1, LOG_RETENTION_ERREURS_JOURS=1,
                      ID_REQUETE_ENTRANT_ACCEPTE=False, ORIGINES_AUTORISEES=())
    bp = Blueprint("essai", __name__, url_prefix="/api")

    @bp.patch("/reservations/<uuid:reservation_id>")
    @documenter("Annuler", tags=("Réservations",), corps=dto.AnnulationEntree,
                reponses={200: dto.ReservationSortie}, erreurs=(404,))
    def annuler(reservation_id):
        return jsonify({"id": str(reservation_id)})

    annuler.roles_autorises = ("gestionnaire",)

    @bp.get("/planning")
    @documenter("Planning", tags=("Planning",), parametres=dto.PlanningParametres,
                reponses={200: dto.PlanningSortie})
    def planning():
        return jsonify({})

    @bp.get("/salles")
    @documenter("Salles", tags=("Salles",), reponses={200: [dto.SalleSortie]})
    def salles():
        return jsonify([])

    @bp.post("/echo")
    def echo():
        return jsonify({"ok": True})

    @bp.get("/sante")
    @documenter("Santé", tags=("Système",), reponses={200: None})
    @route_publique
    def sante():
        return jsonify({})

    @bp.get("/interdit")
    def interdit():
        return jsonify({"code": "role_insuffisant"}), 403

    @bp.get("/flux")
    def flux():
        def evenements():
            yield "retry: 3000\n\n"
            raise AssertionError("le flux a été lu en entier avant d'être envoyé")

        return Response(evenements(), mimetype="text/event-stream")

    app.register_blueprint(bp)
    configurer_journalisation(app)
    configurer_securite_http(app)
    return app


def test_document_openapi(appli):
    document = generer_openapi(appli)
    operation = document["paths"]["/api/reservations/{reservation_id}"]["patch"]
    assert operation["parameters"][0] == {
        "name": "reservation_id", "in": "path", "required": True,
        "schema": {"type": "string", "format": "uuid"}}
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"] \
        .startswith("#/components/schemas/AnnulationEntree")
    assert {"200", "400", "401", "403", "404"} <= set(operation["responses"])
    assert "gestionnaire" in operation["description"]
    assert "X-CSRF-TOKEN" in operation["description"]

    parametres = document["paths"]["/api/planning"]["get"]["parameters"]
    assert [p["name"] for p in parametres] == ["date"]
    assert "PlanningSortie" in document["components"]["schemas"]
    liste = document["paths"]["/api/salles"]["get"]["responses"]["200"]["content"]
    assert liste["application/json"]["schema"]["type"] == "array"
    json.dumps(document)  # sérialisable tel quel


def test_une_route_publique_est_documentee_sans_authentification(appli):
    document = generer_openapi(appli)
    sante = document["paths"]["/api/sante"]["get"]
    assert sante["security"] == []
    assert "401" not in sante["responses"]
    assert document["paths"]["/api/planning"]["get"]["security"] == [{"cookieAuth": []}]


def test_entetes_de_securite(appli):
    reponse = appli.test_client().get("/api/planning")
    assert reponse.headers["X-Content-Type-Options"] == "nosniff"
    assert reponse.headers["X-Frame-Options"] == "DENY"
    assert reponse.headers["Content-Security-Policy"].startswith("default-src 'none'")
    assert reponse.headers["Cache-Control"] == "no-store"
    assert "max-age" in reponse.headers["Strict-Transport-Security"]
    assert reponse.headers["X-Request-ID"]


def test_corps_non_json_refuse_en_415(appli):
    client = appli.test_client()
    reponse = client.post("/api/echo", data="a=1",
                          content_type="application/x-www-form-urlencoded")
    assert reponse.status_code == 415
    assert client.post("/api/echo", json={"a": 1}).status_code == 200


def test_une_ligne_json_par_requete(appli, caplog):
    with caplog.at_level(logging.INFO, logger="sae.requetes"):
        appli.test_client().get("/api/planning?date=2026-11-02&token=secret")
    enregistrement = next(r for r in caplog.records if r.name == "sae.requetes")
    ligne = json.loads(FormateurJson().format(enregistrement))
    assert ligne["message"] == "requete.traitee"  # message stable, détails en champs
    assert ligne["niveau"] == "INFO"
    assert ligne["methode"] == "GET"
    assert ligne["route"] == "/api/planning"
    assert ligne["chemin"] == "/api/planning"
    assert ligne["statut"] == 200
    assert ligne["parametres"] == {"date": "2026-11-02", "token": "***"}
    assert "duree_ms" in ligne
    assert "ip" not in ligne  # donnée personnelle : seulement sur les refus


def test_le_journal_ne_lit_pas_un_flux_sse(appli, caplog):
    """Mesurer la taille d'une réponse en flux obligerait Werkzeug à lire tout
    le générateur : le flux temps réel resterait bloqué dans le serveur."""
    with caplog.at_level(logging.INFO, logger="sae.requetes"):
        reponse = appli.test_client().get("/api/flux", buffered=False)
    assert reponse.status_code == 200
    assert next(iter(reponse.response)).startswith(b"retry:")
    reponse.close()
    enregistrement = next(r for r in caplog.records if r.name == "sae.requetes")
    assert enregistrement.taille_reponse is None


def test_le_motif_de_route_regroupe_les_chemins(appli, caplog):
    with caplog.at_level(logging.INFO, logger="sae.requetes"):
        appli.test_client().patch("/api/reservations/7d0a3c5e-8f1b-4a39-9a4e-0c1d2e3f4a5b",
                                  json={})
    enregistrement = next(r for r in caplog.records if r.name == "sae.requetes")
    assert enregistrement.route == "/api/reservations/<uuid:reservation_id>"


def test_un_refus_est_un_avertissement_avec_l_adresse_ip(appli, caplog):
    with caplog.at_level(logging.INFO, logger="sae.requetes"):
        appli.test_client().get("/api/interdit")
    enregistrement = next(r for r in caplog.records if r.name == "sae.requetes")
    assert enregistrement.levelname == "WARNING"
    assert enregistrement.ip == "127.0.0.1"


def test_l_identifiant_de_requete_du_client_n_est_pas_repris_par_defaut(appli):
    client = appli.test_client()
    reponse = client.get("/api/planning", headers={"X-Request-ID": "fourni-par-le-client-123"})
    assert reponse.headers["X-Request-ID"] != "fourni-par-le-client-123"


def test_origine():
    autorisees = frozenset({"http://localhost:5173"})
    assert origine_acceptee(None, "salles.iut.fr", autorisees)  # pas de navigateur
    assert origine_acceptee("https://salles.iut.fr", "salles.iut.fr", autorisees)
    assert origine_acceptee("http://localhost:5173", "localhost:5000", autorisees)
    assert not origine_acceptee("https://site-piege.example", "salles.iut.fr", autorisees)
