"""Configuration de l'application, lue dans les variables d'environnement.

Les noms de variables sont volontairement génériques (SECRET_KEY plutôt que
JWT_SECRET_KEY, APP_ENV plutôt que FLASK_ENV) pour ne pas trahir la pile
technique dans le fichier .env.
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

RACINE_BACKEND = Path(__file__).resolve().parent.parent
LONGUEUR_MIN_SECRET = 32


def _texte(nom: str, defaut: str) -> str:
    """Une variable présente mais vide (copie brute de .env.example) vaut
    « non renseignée » : on garde la valeur par défaut."""
    valeur = os.getenv(nom, "").strip()
    return valeur or defaut


def _entier(nom: str, defaut: int) -> int:
    return int(_texte(nom, str(defaut)))


def _liste(nom: str, defaut: str = "") -> tuple[str, ...]:
    return tuple(v.strip() for v in _texte(nom, defaut).split(",") if v.strip())


def _booleen(nom: str, *, defaut: bool) -> bool:
    valeur = os.getenv(nom)
    if valeur is None or valeur == "":
        return defaut
    return valeur.strip().lower() in {"1", "true", "oui", "yes", "on"}


class Config:
    """Réglages communs. Les valeurs par défaut sont celles de la production :
    un oubli de configuration doit rendre l'application plus sûre, pas moins.
    """

    DEBUG = False
    TESTING = False

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "")
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SECRET_KEY = os.getenv("SECRET_KEY", "")

    # Corps de requête limité : la plus grosse donnée acceptée est une
    # description de 2 000 caractères.
    MAX_CONTENT_LENGTH = 64 * 1024

    # --- Authentification : JWT dans des cookies httpOnly -----------------
    # Le jeton n'est jamais lisible par le JavaScript (protection contre le
    # vol par XSS) ; la protection CSRF repose sur le « double submit »
    # (cookie csrf_* lisible + en-tête X-CSRF-TOKEN) et sur SameSite=Strict.
    JWT_SECRET_KEY = SECRET_KEY
    # Algorithme imposé côté serveur : un jeton qui en annonce un autre
    # (« none », RS256...) est refusé, on ne lit jamais celui de l'en-tête.
    JWT_ALGORITHM = "HS256"
    JWT_DECODE_ALGORITHMS = ["HS256"]
    JWT_TOKEN_LOCATION = ["cookies"]
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(hours=12)
    JWT_COOKIE_SECURE = _booleen("COOKIE_SECURE", defaut=True)
    JWT_COOKIE_SAMESITE = "Strict"
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_ACCESS_COOKIE_PATH = "/api/"
    JWT_REFRESH_COOKIE_PATH = "/api/auth/"
    JWT_SESSION_COOKIE = True  # cookies effacés à la fermeture du navigateur

    # --- Règles métier -------------------------------------------------
    FUSEAU_HORAIRE = "Europe/Paris"
    JOURS_OUVERTURE = (0, 1, 2, 3, 4)  # lundi -> vendredi (date.weekday())
    HORIZON_RESERVATION_JOURS = 60
    DUREE_MAX_ETUDIANT = timedelta(hours=2)  # A-09
    DESCRIPTION_LONGUEUR_MAX = 2000
    EXPORT_PERIODE_MAX_JOURS = 366
    # Connexion : 3 essais libres, puis un délai qui double à chaque échec.
    CONNEXION_ESSAIS_LIBRES = 3
    CONNEXION_DELAI_INITIAL = timedelta(seconds=1)
    CONNEXION_DELAI_MAX = timedelta(minutes=15)

    # --- Durcissement ----------------------------------------------------
    # Limitation de débit par adresse IP : (requêtes, fenêtre en secondes).
    LIMITATION_DEBIT_ACTIVE = True
    LIMITE_GLOBALE = (300, 60)
    LIMITES_PAR_ROUTE = {
        "auth.connexion": (10, 60),
        "auth.inscription": (5, 600),
        "auth.rafraichissement": (30, 60),
        "reservations.exporter_reservations": (10, 60),
    }
    # Nombre de proxys de confiance devant l'API (nginx = 1) : l'adresse du
    # client et le schéma sont alors lus dans X-Forwarded-For / -Proto.
    NB_PROXYS_DE_CONFIANCE = _entier("NB_PROXYS_DE_CONFIANCE", 0)
    # Origines (en plus de celle de l'API) acceptées pour une écriture ou
    # l'ouverture du flux temps réel. Vide en production : front et API sont
    # servis par le même domaine.
    ORIGINES_AUTORISEES = _liste("ORIGINES_AUTORISEES")

    # --- Temps réel (SSE) ----------------------------------------------
    SSE_PULSATION_SECONDES = 15

    # --- Journalisation ------------------------------------------------
    LOG_LEVEL = _texte("LOG_LEVEL", "INFO").upper()
    # Absent : backend/logs ; présent mais vide : console seule (sortie recueillie par systemd).
    LOG_DIR = os.getenv("LOG_DIR", str(RACINE_BACKEND / "logs")).strip()
    LOG_RETENTION_JOURS = _entier("LOG_RETENTION_JOURS", 180)
    LOG_RETENTION_ERREURS_JOURS = _entier("LOG_RETENTION_ERREURS_JOURS", 365)
    # X-Request-ID reçu repris tel quel seulement derrière un proxy qui le pose.
    ID_REQUETE_ENTRANT_ACCEPTE = _booleen("ID_REQUETE_ENTRANT_ACCEPTE", defaut=False)

    # --- En-têtes HTTP -------------------------------------------------
    HSTS_ACTIF = _booleen("HSTS_ACTIF", defaut=True)
    DOCUMENTATION_API_ACTIVE = True


class ConfigDeveloppement(Config):
    DEBUG = True
    JWT_COOKIE_SECURE = _booleen("COOKIE_SECURE", defaut=False)
    HSTS_ACTIF = False
    LOG_LEVEL = _texte("LOG_LEVEL", "DEBUG").upper()
    # Le serveur de développement Vite relaie les appels vers l'API.
    ORIGINES_AUTORISEES = _liste("ORIGINES_AUTORISEES",
                                 "http://localhost:5173,http://127.0.0.1:5173")


class ConfigTest(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = _texte(
        "TEST_DATABASE_URL",
        "postgresql+psycopg2://sae:sae@localhost:5432/sae_salles_test",
    )
    SECRET_KEY = "cle-de-test-uniquement-pas-pour-la-production-0123456789"
    JWT_SECRET_KEY = SECRET_KEY
    JWT_COOKIE_SECURE = False
    HSTS_ACTIF = False
    LOG_DIR = ""
    LOG_LEVEL = "WARNING"
    # La suite enchaîne des centaines de requêtes depuis la même adresse ; la
    # limitation est testée à part (tests/unitaires/test_limitation.py).
    LIMITATION_DEBIT_ACTIVE = False
    # Délai long : le test de force brute ne dépend pas de la vitesse de la machine.
    CONNEXION_DELAI_INITIAL = timedelta(seconds=30)


CONFIGURATIONS: dict[str, type[Config]] = {
    "production": Config,
    "development": ConfigDeveloppement,
    "test": ConfigTest,
}


def choisir_configuration(nom: str | None = None) -> type[Config]:
    """Retourne la classe de configuration correspondant à APP_ENV."""
    nom = (nom or os.getenv("APP_ENV") or "production").strip().lower()
    if nom not in CONFIGURATIONS:
        raise RuntimeError(f"APP_ENV inconnu : {nom!r} ({', '.join(CONFIGURATIONS)})")
    return CONFIGURATIONS[nom]


def verifier_configuration(config: dict) -> None:
    """Refuse de démarrer avec une configuration dangereuse ou incomplète."""
    if not config.get("SQLALCHEMY_DATABASE_URI"):
        raise RuntimeError("DATABASE_URL n'est pas défini (voir backend/.env.example).")
    secret = config.get("JWT_SECRET_KEY") or ""
    if len(secret) < LONGUEUR_MIN_SECRET:
        raise RuntimeError(
            f"SECRET_KEY absent ou trop court (minimum {LONGUEUR_MIN_SECRET} caractères). "
            "Générez-en un avec : python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )
