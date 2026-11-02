"""Limitation de débit par adresse IP (checklist « Durcir son API »).

Deux étages, combinés :
- une limite globale, large, sur toute l'API : elle absorbe un script qui
  boucle ou un robot, sans gêner un utilisateur normal ;
- des limites serrées sur les routes sensibles ou coûteuses (connexion,
  inscription, rafraîchissement, export CSV).
Le troisième étage, par compte, est le délai croissant de la connexion
(services/auth.py).

Fenêtre glissante en mémoire : comme le diffuseur temps réel, elle suppose
un seul processus. Avec plusieurs instances, on porterait ces règles dans un
stockage partagé (Redis, avec flask-limiter) ou dans la passerelle d'API.
"""
import math
import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from flask import Flask, request

from .domaine.erreurs import TropDeTentatives

# Routes jamais limitées : la supervision interroge la santé en boucle.
ROUTES_EXCLUES = frozenset({"systeme.sante"})


@dataclass(frozen=True)
class Limite:
    requetes: int
    fenetre_s: float


class LimiteurDebit:
    """Compte les requêtes par clé sur une fenêtre glissante, sûr entre threads."""

    def __init__(self, horloge: Callable[[], float] = time.monotonic) -> None:
        self._horloge = horloge
        self._passages: dict[str, deque[float]] = defaultdict(deque)
        self._verrou = threading.Lock()

    def consommer(self, cle: str, limite: Limite) -> float:
        """Enregistre une requête. Retourne 0 si elle est acceptée, sinon le
        nombre de secondes à attendre avant que la suivante le soit."""
        instant = self._horloge()
        with self._verrou:
            passages = self._passages[cle]
            while passages and passages[0] <= instant - limite.fenetre_s:
                passages.popleft()
            if len(passages) >= limite.requetes:
                return passages[0] + limite.fenetre_s - instant
            passages.append(instant)
            return 0.0

    def oublier_inactifs(self, fenetre_max_s: float) -> None:
        """Libère la mémoire des clés sans requête récente."""
        seuil = self._horloge() - fenetre_max_s
        with self._verrou:
            for cle in [c for c, p in self._passages.items() if not p or p[-1] <= seuil]:
                del self._passages[cle]


def configurer_limitation(app: Flask) -> None:
    if not app.config["LIMITATION_DEBIT_ACTIVE"]:
        return
    limiteur = LimiteurDebit()
    globale = Limite(*app.config["LIMITE_GLOBALE"])
    par_route: Mapping[str, Limite] = {route: Limite(*valeurs) for route, valeurs
                                       in app.config["LIMITES_PAR_ROUTE"].items()}
    fenetre_max = max([globale.fenetre_s, *(lim.fenetre_s for lim in par_route.values())])
    compteur = {"requetes": 0}

    def verifier_debit() -> None:
        if not request.path.startswith("/api/") or request.endpoint in ROUTES_EXCLUES:
            return
        ip = request.remote_addr or "inconnue"
        attente = limiteur.consommer(f"global:{ip}", globale)
        limite_route = par_route.get(request.endpoint or "")
        if not attente and limite_route is not None:
            attente = limiteur.consommer(f"{request.endpoint}:{ip}", limite_route)
        compteur["requetes"] += 1
        if compteur["requetes"] % 1000 == 0:
            limiteur.oublier_inactifs(fenetre_max)
        if attente:
            raise TropDeTentatives("Trop de requêtes. Réessayez dans un instant.",
                                   code="trop_de_requetes",
                                   reessayer_dans=max(1, math.ceil(attente)))

    app.before_request(verifier_debit)
