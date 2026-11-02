"""Outillage des tests de droits d'accès.

Ces tests tournent contre une vraie base PostgreSQL (TEST_DATABASE_URL,
par défaut sae_salles_test) : les règles de non-chevauchement sont des
contraintes PostgreSQL, un SQLite en mémoire ne prouverait rien.
La base de test est vidée avant chaque test.
"""
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

try:
    from sqlalchemy import text
    from sqlalchemy.exc import OperationalError

    from app import create_app
    from app.cli import _executer_fichier_sql
    from app.domaine.enums import Role
    from app.extensions import db
    from app.persistance.modeles import Batiment, Salle, Utilisateur

    ERREUR_IMPORT: ImportError | None = None
except ImportError as exc:  # dépendances non installées
    ERREUR_IMPORT = exc

PARIS = ZoneInfo("Europe/Paris")
MOT_DE_PASSE = "motdepasse"
# Hash Werkzeug de « motdepasse » (le même que db/seed.sql) : évite de
# recalculer un scrypt pour chaque compte de chaque test.
HASH_MOT_DE_PASSE = (
    "scrypt:32768:8:1$O18DsjXnSdNtr8MY$c47eb9c70d4e57c97b706c121b99fe97a9f141161ec8dba111f4"
    "f4529e94f956e6bc009ddfe517be5befbbd1c41cb96c85c3c37ebe5a565ca7a335015b95a1fb"
)
EMAILS = {
    "etudiant": "etud@iut.fr",
    "etudiant2": "etud2@iut.fr",
    "enseignant": "prof@iut.fr",
    "gestionnaire": "gest@iut.fr",
}
NOMS_COMPLETS = {"etudiant": "Étudiant", "etudiant2": "Étudiant",
                 "enseignant": "Professeur", "gestionnaire": "Gestionnaire"}


@dataclass(frozen=True)
class Jeu:
    """Identifiants du jeu de données créé avant chaque test."""

    etudiant: uuid.UUID
    etudiant2: uuid.UUID
    enseignant: uuid.UUID
    gestionnaire: uuid.UUID
    batiment: uuid.UUID
    salle: uuid.UUID
    salle2: uuid.UUID
    jour: date


def prochain_jour_ouvert() -> date:
    jour = datetime.now(PARIS).date() + timedelta(days=1)
    while jour.weekday() >= 5:
        jour += timedelta(days=1)
    return jour


def creneau(jour: date, debut: int, fin: int) -> dict[str, str]:
    """Plage horaire au format attendu par l'API (heure de Paris, sans fuseau)."""
    return {"debut": f"{jour.isoformat()}T{debut:02d}:00",
            "fin": f"{jour.isoformat()}T{fin:02d}:00"}


class ClientApi:
    """Client de test qui recopie le cookie CSRF dans l'en-tête, comme le
    fait le frontend."""

    def __init__(self, client: Any) -> None:
        self.client = client

    # Chemins des cookies posés par l'API (le client de test les distingue).
    CHEMINS_COOKIES = {"access_token_cookie": "/api/", "refresh_token_cookie": "/api/auth/"}

    def cookie(self, nom: str) -> str:
        trouve = self.client.get_cookie(nom, path=self.CHEMINS_COOKIES.get(nom, "/"))
        return trouve.value if trouve is not None else ""

    def _entetes(self, csrf: bool, cookie_csrf: str) -> dict[str, str]:
        return {"X-CSRF-TOKEN": self.cookie(cookie_csrf)} if csrf else {}

    def connexion(self, email: str, mot_de_passe: str = MOT_DE_PASSE):
        return self.client.post("/api/auth/connexion",
                                json={"email": email, "mot_de_passe": mot_de_passe})

    def get(self, url: str):
        return self.client.get(url)

    def post(self, url: str, json: Any = None, csrf: bool = True,
             cookie_csrf: str = "csrf_access_token"):
        return self.client.post(url, json=json, headers=self._entetes(csrf, cookie_csrf))

    def patch(self, url: str, json: Any = None, csrf: bool = True):
        return self.client.patch(url, json=json,
                                 headers=self._entetes(csrf, "csrf_access_token"))

    def delete(self, url: str, csrf: bool = True):
        return self.client.delete(url, headers=self._entetes(csrf, "csrf_access_token"))

    def reserver(self, salle_id: uuid.UUID, jour: date, debut: int, fin: int,
                 description: str = "Travail de groupe"):
        return self.post("/api/reservations", json={
            "salle_id": str(salle_id), **creneau(jour, debut, fin), "description": description,
        })


@pytest.fixture(scope="session")
def app():
    if ERREUR_IMPORT is not None:
        pytest.skip(f"Dépendances absentes ({ERREUR_IMPORT}) : "
                    "pip install -r requirements-dev.txt")
    application = create_app("test")
    with application.app_context():
        try:
            db.session.execute(text("SELECT 1"))
        except OperationalError as exc:
            pytest.skip("Base de test injoignable : démarrez PostgreSQL et vérifiez "
                        f"TEST_DATABASE_URL ({exc.orig})")
        finally:
            db.session.remove()
        _executer_fichier_sql("schema.sql")
    return application


@pytest.fixture
def jeu(app) -> Jeu:
    with app.app_context():
        db.session.execute(text(
            "TRUNCATE fermeture, reservation, salle, batiment, session_utilisateur, "
            "verrou_connexion, utilisateur CASCADE"
        ))
        roles = {"etudiant": Role.ETUDIANT, "etudiant2": Role.ETUDIANT,
                 "enseignant": Role.ENSEIGNANT, "gestionnaire": Role.GESTIONNAIRE}
        comptes = {
            cle: Utilisateur(email=EMAILS[cle], nom="IUT", prenom=NOMS_COMPLETS[cle],
                             role=role, mot_de_passe=HASH_MOT_DE_PASSE)
            for cle, role in roles.items()
        }
        batiment = Batiment(code="D", nom="Bâtiment D")
        db.session.add_all([*comptes.values(), batiment])
        db.session.flush()
        salles = [
            Salle(code=code, batiment_id=batiment.id, capacite=8,
                  heure_ouverture=time(8), heure_fermeture=time(20))
            for code in ("D101", "D102")
        ]
        db.session.add_all(salles)
        db.session.commit()
        donnees = Jeu(
            **{cle: compte.id for cle, compte in comptes.items()},
            batiment=batiment.id, salle=salles[0].id, salle2=salles[1].id,
            jour=prochain_jour_ouvert(),
        )
        db.session.remove()
    return donnees


@pytest.fixture
def anonyme(app) -> ClientApi:
    return ClientApi(app.test_client())


@pytest.fixture
def connecte(app, jeu):
    """Fabrique de clients connectés : connecte("etudiant"), connecte("gestionnaire")..."""

    def fabrique(role: str) -> ClientApi:
        client = ClientApi(app.test_client())
        reponse = client.connexion(EMAILS[role])
        assert reponse.status_code == 200, reponse.get_json()
        return client

    return fabrique
