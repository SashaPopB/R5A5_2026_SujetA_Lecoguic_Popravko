"""Configuration lue dans l'environnement."""
import importlib
from pathlib import Path

import pytest

import app.config


@pytest.fixture
def config_rechargee(monkeypatch):
    def recharger(**variables):
        for nom, valeur in variables.items():
            monkeypatch.setenv(nom, valeur)
        return importlib.reload(app.config)

    yield recharger
    monkeypatch.undo()
    importlib.reload(app.config)


def test_une_copie_brute_de_env_example_ne_casse_rien(config_rechargee):
    """Chaque ligne active du vrai fichier .env.example, telle quelle."""
    exemple = Path(__file__).resolve().parents[2] / ".env.example"
    lignes = [ligne.split("=", 1) for ligne in exemple.read_text(encoding="utf-8").splitlines()
              if ligne.strip() and not ligne.startswith("#")]
    module = config_rechargee(**{nom.strip(): valeur.strip() for nom, valeur in lignes})
    assert module.Config.LOG_DIR.endswith("logs")  # fichiers de journal conservés
    assert module.Config.HSTS_ACTIF is True
    assert module.ConfigDeveloppement.LOG_LEVEL == "DEBUG"
    assert module.Config.LOG_LEVEL == "INFO"
    assert module.Config.LOG_RETENTION_JOURS == 180
    assert module.Config.NB_PROXYS_DE_CONFIANCE == 0
    assert module.Config.JWT_COOKIE_SECURE is True
    assert module.choisir_configuration() is module.Config  # production par défaut
    assert "http://localhost:5173" in module.ConfigDeveloppement.ORIGINES_AUTORISEES
    assert module.ConfigTest.SQLALCHEMY_DATABASE_URI.startswith("postgresql")


def test_secret_trop_court_refuse():
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        app.config.verifier_configuration({"SQLALCHEMY_DATABASE_URI": "postgresql://x",
                                           "JWT_SECRET_KEY": "court"})
