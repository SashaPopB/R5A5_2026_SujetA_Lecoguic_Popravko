"""Flux temps réel (Server-Sent Events) pour le planning (A-04)."""
import random

from flask import Blueprint, Response, current_app, g, request, stream_with_context
from flask_jwt_extended import get_jwt

from ...extensions import db, diffuseur
from ...temps_reel import ReglagesFlux, flux_sse
from .. import dto
from ..openapi import documenter
from ..validation import lire_parametres

bp = Blueprint("evenements", __name__, url_prefix="/api")

# Délai de reconnexion tiré au hasard : après un redémarrage du serveur, les
# clients ne reviennent pas tous à la même seconde.
RETRY_MIN_MS, RETRY_MAX_MS = 2000, 5000
LONGUEUR_MAX_ID = 64


@bp.get("/evenements")
@documenter("Flux des changements du planning (SSE)", tags=("Temps réel",),
            type_contenu="text/event-stream", parametres=dto.EvenementsParametres,
            reponses={200: "Flux text/event-stream : `connecte` ({type, reprise}), puis "
                           "`planning` ({type: planning, salle_id, jours} ou {type: salles} "
                           "ou {type: resynchronisation}), chacun avec un `id:`."},
            description="À ouvrir avec `new EventSource('/api/evenements')` : le cookie "
                        "d'accès suffit. À la reconnexion, le navigateur renvoie l'en-tête "
                        "`Last-Event-ID` (ou le client passe `?depuis=<id>`) : les événements "
                        "manqués sont rejoués (`reprise: complete`) ou, s'ils sont trop "
                        "anciens, le client doit recharger le planning "
                        "(`reprise: impossible`). Le flux se ferme à l'expiration du jeton "
                        "(15 min) ; le client rafraîchit sa session puis se reconnecte.")
def flux_evenements():
    parametres = lire_parametres(dto.EvenementsParametres)
    dernier_id = request.headers.get("Last-Event-ID", "")[:LONGUEUR_MAX_ID] or parametres.depuis
    abonnement = diffuseur.abonner(dernier_id)
    reglages = ReglagesFlux(
        pulsation=float(current_app.config["SSE_PULSATION_SECONDES"]),
        fin_validite=float(get_jwt()["exp"]),
        retry_ms=random.randint(RETRY_MIN_MS, RETRY_MAX_MS),  # noqa: S311 (pas de sécurité ici)
    )
    contexte = {"id_requete": g.get("id_requete"), "utilisateur": g.get("utilisateur_id")}
    # La connexion SQL utilisée pour l'authentification retourne au pool :
    # sans cela, chaque client connecté immobiliserait une connexion.
    db.session.close()
    flux = flux_sse(abonnement, diffuseur, reglages, contexte)
    return Response(stream_with_context(flux), mimetype="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",  # désactive la mise en tampon d'un éventuel nginx
    })
