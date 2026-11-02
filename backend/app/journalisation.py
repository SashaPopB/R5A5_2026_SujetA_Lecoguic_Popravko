"""Journalisation (voir docs/adr/03-journalisation.md).

- Format : JSON Lines, un objet par ligne, avec une liste fixe de noms de
  champs (lisible par un humain, filtrable par jq, Loki, Elasticsearch...).
  Le message est un nom d'événement stable (« requete.traitee »,
  « reservation.creee ») ; tout ce qui se compte ou se filtre est un champ.
- Destination : la console (seule destination si LOG_DIR est vide) et, sur un
  serveur, logs/api.log (tout) et logs/erreurs.log (ERROR et plus, gardé plus
  longtemps), avec rotation quotidienne et rétention limitée.
- Une ligne par requête HTTP, écrite au départ de la réponse (méthode, motif
  de route, chemin, statut, durée, utilisateur, exception éventuelle), une
  ligne par événement métier, une ligne à part pour la pile d'un 500.
- Jamais de mot de passe, de jeton, d'adresse e-mail ni de corps de requête.
  L'adresse IP n'est écrite que sur les refus (401, 403, 429) : c'est la
  seule finalité qui la justifie (détection d'attaques).
"""
import json
import logging
import re
import time
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from flask import Flask, Response, g, request

journal_requetes = logging.getLogger("sae.requetes")

# Attributs propres à logging.LogRecord : tout le reste est un champ ajouté.
ATTRIBUTS_STANDARD = frozenset(vars(logging.makeLogRecord({}))) | {"message", "asctime"}
_ID_REQUETE_VALIDE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
STATUTS_REFUS = {HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN, HTTPStatus.TOO_MANY_REQUESTS}
# Paramètres de query string jamais recopiés dans le journal.
_PARAMETRES_SENSIBLES = {"token", "jeton", "mot_de_passe", "password"}


class FormateurJson(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        donnees = {
            "horodatage": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds"),
            "niveau": record.levelname,
            "journal": record.name,
            "message": record.getMessage(),
        }
        donnees.update({cle: valeur for cle, valeur in vars(record).items()
                        if cle not in ATTRIBUTS_STANDARD and not cle.startswith("_")})
        if record.exc_info:
            donnees["trace"] = self.formatException(record.exc_info)
        return json.dumps(donnees, ensure_ascii=False, default=str)


def configurer_journalisation(app: Flask) -> None:
    racine = logging.getLogger("sae")
    racine.setLevel(app.config["LOG_LEVEL"])
    racine.propagate = False
    racine.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(FormateurJson())
    racine.addHandler(console)

    dossier = app.config["LOG_DIR"]
    if dossier:
        Path(dossier).mkdir(parents=True, exist_ok=True)
        racine.addHandler(_fichier_tournant(Path(dossier) / "api.log",
                                            app.config["LOG_RETENTION_JOURS"]))
        erreurs = _fichier_tournant(Path(dossier) / "erreurs.log",
                                    app.config["LOG_RETENTION_ERREURS_JOURS"])
        erreurs.setLevel(logging.ERROR)
        racine.addHandler(erreurs)

    # Werkzeug journalise aussi chaque requête : on le fait déjà, avec plus
    # d'informations. Inutile d'écrire deux fois la même chose.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    # Enregistré avant toute autre vérification (type de contenu, débit,
    # authentification) : les requêtes qu'elles rejettent sont journalisées.
    accepter_id_entrant = app.config["ID_REQUETE_ENTRANT_ACCEPTE"]

    def debut_requete() -> None:
        g.debut_requete = time.perf_counter()
        # Un identifiant reçu n'est repris que derrière un proxy de confiance
        # qui le fabrique : un client externe pourrait envoyer n'importe quoi.
        fourni = request.headers.get("X-Request-ID", "") if accepter_id_entrant else ""
        g.id_requete = fourni if _ID_REQUETE_VALIDE.match(fourni) else uuid.uuid4().hex

    app.before_request(debut_requete)
    app.after_request(_journaliser_requete)


def _fichier_tournant(chemin: Path, retention_jours: int) -> TimedRotatingFileHandler:
    """Un fichier par jour ; au-delà de la rétention, les plus anciens sont
    supprimés automatiquement."""
    fichier = TimedRotatingFileHandler(chemin, when="midnight", utc=True,
                                       backupCount=retention_jours, encoding="utf-8")
    fichier.setFormatter(FormateurJson())
    return fichier


def _parametres_filtres() -> dict[str, str]:
    return {cle: ("***" if cle.lower() in _PARAMETRES_SENSIBLES else valeur)
            for cle, valeur in request.args.items()}


def _journaliser_requete(reponse: Response) -> Response:
    debut = g.get("debut_requete", time.perf_counter())
    statut = reponse.status_code
    niveau = (logging.ERROR if statut >= HTTPStatus.INTERNAL_SERVER_ERROR
              else logging.WARNING if statut >= HTTPStatus.BAD_REQUEST else logging.INFO)
    extra = {
        "id_requete": g.get("id_requete"),
        "methode": request.method,
        # Motif de route (/api/reservations/<uuid:reservation_id>) pour
        # regrouper et compter ; le chemin réel reste dans « chemin ».
        "route": request.url_rule.rule if request.url_rule else None,
        "chemin": request.path,
        "parametres": _parametres_filtres() or None,
        "statut": statut,
        "duree_ms": round((time.perf_counter() - debut) * 1000, 1),
        "taille_requete": request.content_length,
        # Jamais calculée sur une réponse en flux (SSE) : Werkzeug lirait tout
        # le générateur pour la mesurer, et le flux ne partirait jamais.
        "taille_reponse": None if reponse.is_streamed else reponse.calculate_content_length(),
        "agent": request.user_agent.string[:200] or None,
        "utilisateur": g.get("utilisateur_id"),
    }
    if statut in STATUTS_REFUS:
        extra["ip"] = request.remote_addr
    erreur = g.get("erreur")
    if erreur:
        extra["exception"], extra["detail"] = erreur
    journal_requetes.log(niveau, "requete.traitee", extra=extra)
    reponse.headers["X-Request-ID"] = g.get("id_requete", "")
    return reponse
