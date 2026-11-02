"""Limitation de débit par adresse IP."""
from http import HTTPStatus

from flask import Flask, jsonify

from app.domaine.erreurs import TropDeTentatives
from app.limitation import Limite, LimiteurDebit, configurer_limitation


class HorlogeManuelle:
    def __init__(self) -> None:
        self.instant = 0.0

    def __call__(self) -> float:
        return self.instant


def test_fenetre_glissante():
    horloge = HorlogeManuelle()
    limiteur = LimiteurDebit(horloge)
    limite = Limite(requetes=2, fenetre_s=60)
    assert limiteur.consommer("ip", limite) == 0
    horloge.instant = 10
    assert limiteur.consommer("ip", limite) == 0
    horloge.instant = 20
    assert limiteur.consommer("ip", limite) == 40  # la 1re requête sort de la fenêtre à 60 s
    assert limiteur.consommer("autre-ip", limite) == 0  # chaque adresse a son compteur
    horloge.instant = 61
    assert limiteur.consommer("ip", limite) == 0


def test_les_compteurs_inactifs_sont_oublies():
    horloge = HorlogeManuelle()
    limiteur = LimiteurDebit(horloge)
    limiteur.consommer("ip", Limite(1, 60))
    horloge.instant = 120
    limiteur.oublier_inactifs(60)
    assert limiteur.consommer("ip", Limite(1, 60)) == 0


def _appli(**reglages) -> Flask:
    app = Flask(__name__)
    app.config.update({"LIMITATION_DEBIT_ACTIVE": True, "LIMITE_GLOBALE": (100, 60),
                       "LIMITES_PAR_ROUTE": {"connexion": (2, 60)}, **reglages})

    @app.post("/api/auth/connexion", endpoint="connexion")
    def connexion():
        return jsonify({})

    @app.get("/api/sante", endpoint="systeme.sante")
    def sante():
        return jsonify({})

    @app.errorhandler(TropDeTentatives)
    def trop(erreur):
        return jsonify({"code": erreur.code}), HTTPStatus.TOO_MANY_REQUESTS, {
            "Retry-After": str(erreur.reessayer_dans)}

    configurer_limitation(app)
    return app


def test_limite_serree_sur_la_connexion():
    client = _appli().test_client()
    assert [client.post("/api/auth/connexion").status_code for _ in range(3)] == [200, 200, 429]
    refus = client.post("/api/auth/connexion")
    assert refus.get_json() == {"code": "trop_de_requetes"}
    assert int(refus.headers["Retry-After"]) >= 1


def test_la_sante_n_est_jamais_limitee():
    client = _appli(LIMITE_GLOBALE=(1, 60)).test_client()
    assert {client.get("/api/sante").status_code for _ in range(5)} == {200}
