"""Diffusion des changements du planning en temps réel (A-04).

Mécanisme retenu : Server-Sent Events (voir docs/adr/02-temps-reel.md).

- Chaque client connecté à GET /api/evenements possède une file ; un
  changement validé en base est publié dans toutes les files (pub/sub).
- Chaque événement porte un identifiant `id:` ; les derniers événements sont
  gardés en mémoire. À la reconnexion, le navigateur renvoie le dernier
  identifiant reçu (en-tête Last-Event-ID) : on rejoue les événements manqués
  s'ils sont encore dans l'historique, sinon on demande au client de
  recharger son planning (snapshot puis deltas).
- Les événements ne transportent aucune donnée personnelle : le type de
  changement, la salle et les jours touchés. Le client recharge le planning
  par l'API habituelle, qui applique les règles de visibilité. La base reste
  la référence : un événement perdu ne rend jamais l'affichage faux
  durablement.

Limite assumée : le diffuseur vit dans le processus. Avec plusieurs
processus il faudrait un bus partagé (LISTEN/NOTIFY de PostgreSQL ou Redis) ;
on déploie donc un seul processus multi-threadé (gunicorn -k gthread).
"""
import json
import logging
import queue
import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any, Literal

TAILLE_FILE_PAR_CLIENT = 100
TAILLE_HISTORIQUE = 500
EVENEMENT_RESYNCHRONISATION = {"type": "resynchronisation"}

Reprise = Literal["initiale", "complete", "impossible"]

journal_temps_reel = logging.getLogger("sae.temps_reel")


@dataclass(frozen=True)
class Abonnement:
    file: "queue.Queue[str]"
    # initiale : premier abonnement ; complete : les événements manqués sont
    # dans la file ; impossible : trop ancien, le client doit tout recharger.
    reprise: Reprise


class DiffuseurEvenements:
    """Publication / abonnement en mémoire, sûr entre threads."""

    def __init__(self, taille_file: int = TAILLE_FILE_PAR_CLIENT,
                 taille_historique: int = TAILLE_HISTORIQUE) -> None:
        self._taille_file = taille_file
        self._abonnes: set[queue.Queue[str]] = set()
        self._verrou = threading.Lock()
        self._compteur = 0
        self._historique: deque[tuple[int, str]] = deque(maxlen=taille_historique)
        # Préfixe des identifiants : après un redémarrage, les anciens
        # identifiants ne désignent plus rien et sont reconnus comme tels.
        self._epoque = format(time.time_ns(), "x")
        self.evenements_publies = 0
        self.resynchronisations = 0

    @property
    def nombre_abonnes(self) -> int:
        with self._verrou:
            return len(self._abonnes)

    def abonner(self, dernier_id: str | None = None) -> Abonnement:
        """Nouvel abonné. Avec `dernier_id` (Last-Event-ID), la file est
        préremplie avec les événements publiés depuis."""
        file: queue.Queue[str] = queue.Queue(maxsize=self._taille_file)
        reprise: Reprise = "initiale"
        with self._verrou:  # même verrou que publier() : aucun événement ne passe entre les deux
            if dernier_id:
                manques = self._publies_apres(dernier_id)
                if manques is None or len(manques) > self._taille_file:
                    reprise = "impossible"
                    self.resynchronisations += 1
                else:
                    reprise = "complete"
                    for message in manques:
                        file.put_nowait(message)
            self._abonnes.add(file)
        return Abonnement(file, reprise)

    def desabonner(self, file: "queue.Queue[str]") -> None:
        with self._verrou:
            self._abonnes.discard(file)

    def publier(self, evenement: dict[str, Any]) -> None:
        """Pousse l'événement à tous les abonnés, sans jamais bloquer.

        Un client trop lent (file pleine) ne doit pas ralentir les autres :
        on vide sa file et on lui demande de se resynchroniser entièrement.
        """
        with self._verrou:
            self._compteur += 1
            message = formater_sse(evenement, identifiant=f"{self._epoque}.{self._compteur}")
            self._historique.append((self._compteur, message))
            self.evenements_publies += 1
            abonnes = list(self._abonnes)
        for file in abonnes:
            try:
                file.put_nowait(message)
            except queue.Full:
                _vider(file)
                file.put_nowait(formater_sse(EVENEMENT_RESYNCHRONISATION))
                self.resynchronisations += 1

    def _publies_apres(self, dernier_id: str) -> list[str] | None:
        """Messages publiés après `dernier_id`, ou None s'ils ne sont plus tous
        connus (autre démarrage du serveur, historique dépassé)."""
        epoque, _, numero = dernier_id.partition(".")
        if epoque != self._epoque or not numero.isdigit():
            return None
        dernier = int(numero)
        if dernier > self._compteur:
            return None
        plus_ancien = self._historique[0][0] if self._historique else self._compteur + 1
        if dernier < plus_ancien - 1:
            return None
        return [message for identifiant, message in self._historique if identifiant > dernier]


def _vider(file: "queue.Queue[str]") -> None:
    try:
        while True:
            file.get_nowait()
    except queue.Empty:
        pass


def formater_sse(donnees: dict[str, Any], identifiant: str | None = None,
                 nom: str = "planning") -> str:
    """Sérialise un événement au format text/event-stream."""
    lignes = []
    if identifiant is not None:
        lignes.append(f"id: {identifiant}")
    lignes.append(f"event: {nom}")
    lignes.append(f"data: {json.dumps(donnees, ensure_ascii=False, separators=(',', ':'))}")
    return "\n".join(lignes) + "\n\n"


@dataclass(frozen=True)
class ReglagesFlux:
    pulsation: float          # secondes entre deux commentaires de maintien
    fin_validite: float       # instant (epoch) d'expiration du jeton d'accès
    retry_ms: int             # délai de reconnexion conseillé au navigateur
    horloge: Callable[[], float] = time.time


def flux_sse(abonnement: Abonnement, diffuseur: DiffuseurEvenements, reglages: ReglagesFlux,
             contexte: dict[str, Any]) -> Iterator[str]:
    """Générateur de la réponse SSE d'un client.

    - « retry » fixe le délai de reconnexion automatique du navigateur ;
    - une pulsation (commentaire « : ») part régulièrement : elle évite que
      les proxys coupent une connexion silencieuse et révèle un client parti
      (l'écriture échoue, le générateur est fermé) ;
    - le flux se ferme à l'expiration du jeton d'accès : le client rafraîchit
      sa session puis se reconnecte, ce qui revérifie ses droits ;
    - une ligne de journal à l'ouverture et une à la fermeture (avec le
      motif) : on suit les connexions sans journaliser chaque message.
    """
    debut = reglages.horloge()
    envoyes = 0
    motif = "client_parti"
    journal_temps_reel.info("flux.ouvert", extra={
        **contexte, "reprise": abonnement.reprise,
        "connexions_actives": diffuseur.nombre_abonnes})
    try:
        yield f"retry: {reglages.retry_ms}\n\n"
        yield formater_sse({"type": "connecte", "reprise": abonnement.reprise}, nom="connecte")
        while True:
            restant = reglages.fin_validite - reglages.horloge()
            if restant <= 0:
                motif = "jeton_expire"
                return
            try:
                message = abonnement.file.get(timeout=min(reglages.pulsation, restant))
            except queue.Empty:
                yield ": pulsation\n\n"
            else:
                envoyes += 1
                yield message
    except Exception:
        motif = "erreur"
        journal_temps_reel.exception("flux.erreur", extra=contexte)
        raise
    finally:
        diffuseur.desabonner(abonnement.file)
        journal_temps_reel.info("flux.ferme", extra={
            **contexte, "motif": motif, "duree_s": round(reglages.horloge() - debut, 1),
            "evenements_envoyes": envoyes, "connexions_actives": diffuseur.nombre_abonnes})
