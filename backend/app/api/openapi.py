"""Documentation OpenAPI 3.1 générée à partir du code.

Chaque route porte un décorateur @documenter qui référence ses DTO
pydantic ; le document est reconstruit à partir de la table de routage de
Flask. La documentation ne peut donc pas diverger du code : les classes qui
valident les entrées sont celles qui décrivent l'API.

Swagger UI est servi sur /api/docs, le document brut sur /api/openapi.json.

Ce module porte aussi la marque @route_publique (exception au refus par
défaut) : la sécurité (securite.py) et la documentation lisent la même
marque, il n'y a qu'une source de vérité.
"""
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import Any, Literal, TypeVar

from flask import Blueprint, Flask, Response, current_app, jsonify
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from .dto import ErreurSortie

V = TypeVar("V", bound=Callable[..., Any])
Mode = Literal["validation", "serialization"]

VERSION_SWAGGER_UI = "5.17.14"
_PARAMETRE_ROUTE = re.compile(r"<(?:(?P<convertisseur>\w+)(?:\([^)]*\))?:)?(?P<nom>\w+)>")
_SCHEMAS_CONVERTISSEURS = {
    "uuid": {"type": "string", "format": "uuid"},
    "int": {"type": "integer"},
}
_REPONSES_ERREUR = {
    HTTPStatus.BAD_REQUEST: "Données invalides",
    HTTPStatus.UNAUTHORIZED: "Non authentifié, session expirée ou jeton CSRF manquant",
    HTTPStatus.FORBIDDEN: "Authentifié mais pas autorisé",
    HTTPStatus.NOT_FOUND: "Ressource introuvable",
    HTTPStatus.CONFLICT: "Conflit avec l'état actuel (créneau déjà pris, salle fermée...)",
    HTTPStatus.TOO_MANY_REQUESTS: "Trop d'essais, réessayer plus tard (en-tête Retry-After)",
}


@dataclass(frozen=True)
class Documentation:
    resume: str
    tags: tuple[str, ...]
    # Code HTTP -> Modele, [Modele] (tableau), description texte, ou None (sans corps)
    reponses: Mapping[int, Any]
    corps: type[BaseModel] | None = None
    parametres: type[BaseModel] | None = None
    description: str = ""
    type_contenu: str = "application/json"
    erreurs: tuple[int, ...] = field(default_factory=tuple)


def route_publique(vue: V) -> V:
    """Route accessible sans session. Chaque usage est une décision."""
    vue.route_publique = True  # type: ignore[attr-defined]
    return vue


def est_publique(vue: Callable[..., Any]) -> bool:
    return bool(getattr(vue, "route_publique", False))


def _modele_de(contenu: Any) -> type[BaseModel] | None:
    """Modèle pydantic d'une réponse : `Modele` ou `[Modele]` (tableau)."""
    if isinstance(contenu, list) and len(contenu) == 1:
        contenu = contenu[0]
    if isinstance(contenu, type) and issubclass(contenu, BaseModel):
        return contenu
    return None


def documenter(resume: str, *, tags: tuple[str, ...], reponses: Mapping[int, Any],
               **options: Any) -> Callable[[V], V]:
    def decorateur(vue: V) -> V:
        vue.__documentation__ = Documentation(  # type: ignore[attr-defined]
            resume=resume, tags=tags, reponses=reponses, **options)
        return vue

    return decorateur


def _chemin_openapi(regle: str) -> tuple[str, list[dict[str, Any]]]:
    parametres = []
    for correspondance in _PARAMETRE_ROUTE.finditer(regle):
        schema = _SCHEMAS_CONVERTISSEURS.get(correspondance["convertisseur"] or "",
                                             {"type": "string"})
        parametres.append({"name": correspondance["nom"], "in": "path",
                           "required": True, "schema": schema})
    return _PARAMETRE_ROUTE.sub(lambda m: "{" + m["nom"] + "}", regle), parametres


def generer_openapi(app: Flask) -> dict[str, Any]:
    operations: list[tuple[str, str, Callable[..., Any], Documentation]] = []
    modeles: set[tuple[type[BaseModel], Mode]] = {(ErreurSortie, "serialization")}

    for regle in app.url_map.iter_rules():
        vue = app.view_functions.get(regle.endpoint)
        doc: Documentation | None = getattr(vue, "__documentation__", None)
        if vue is None or doc is None:
            continue
        for methode in sorted((regle.methods or set()) - {"HEAD", "OPTIONS"}):
            operations.append((regle.rule, methode, vue, doc))
        if doc.corps:
            modeles.add((doc.corps, "validation"))
        if doc.parametres:
            modeles.add((doc.parametres, "validation"))
        for reponse in doc.reponses.values():
            modele = _modele_de(reponse)
            if modele is not None:
                modeles.add((modele, "serialization"))

    references, schemas = models_json_schema(
        sorted(modeles, key=lambda m: (m[0].__name__, m[1])),
        ref_template="#/components/schemas/{model}",
    )
    definitions = schemas.get("$defs", {})

    def reference(modele: type[BaseModel], mode: Mode) -> dict[str, Any]:
        return references[(modele, mode)]

    chemins: dict[str, dict[str, Any]] = {}
    for regle, methode, vue, doc in sorted(operations, key=lambda o: (o[0], o[1])):
        chemin, parametres = _chemin_openapi(regle)
        if doc.parametres:
            nom_schema = reference(doc.parametres, "validation")["$ref"].rsplit("/", 1)[-1]
            schema_parametres = definitions[nom_schema]
            obligatoires = set(schema_parametres.get("required", []))
            for nom, propriete in schema_parametres.get("properties", {}).items():
                parametres.append({"name": nom, "in": "query", "required": nom in obligatoires,
                                   "schema": propriete,
                                   "description": propriete.get("description", "")})

        description = doc.description
        publique = est_publique(vue)
        roles = getattr(vue, "roles_autorises", None)
        if roles:
            description += "\n\n**Rôles autorisés :** " + ", ".join(str(r) for r in roles)
        if not publique and methode in {"POST", "PUT", "PATCH", "DELETE"}:
            description += ("\n\n**CSRF :** recopier le cookie `csrf_access_token` dans "
                            "l'en-tête `X-CSRF-TOKEN`.")

        reponses: dict[str, Any] = {}
        for code, contenu in doc.reponses.items():
            libelle = HTTPStatus(code).phrase
            modele = _modele_de(contenu)
            if modele is not None:
                schema = reference(modele, "serialization")
                if isinstance(contenu, list):  # [Modele] : la réponse est un tableau
                    schema = {"type": "array", "items": schema}
                reponses[str(code)] = {"description": libelle, "content": {
                    "application/json": {"schema": schema}}}
            elif isinstance(contenu, str):
                reponses[str(code)] = {"description": contenu, "content": {
                    doc.type_contenu: {"schema": {"type": "string"}}}}
            else:
                reponses[str(code)] = {"description": libelle}
        erreurs = set(doc.erreurs) | ({HTTPStatus.UNAUTHORIZED} if not publique else set())
        if doc.corps or doc.parametres:
            erreurs.add(HTTPStatus.BAD_REQUEST)
        if roles:
            erreurs.add(HTTPStatus.FORBIDDEN)
        for code in sorted(erreurs):
            reponses.setdefault(str(int(code)), {
                "description": _REPONSES_ERREUR.get(HTTPStatus(code), HTTPStatus(code).phrase),
                "content": {"application/json": {
                    "schema": reference(ErreurSortie, "serialization")}},
            })

        operation: dict[str, Any] = {
            "operationId": f"{vue.__name__}_{methode.lower()}",
            "summary": doc.resume,
            "description": description.strip(),
            "tags": list(doc.tags),
            "parameters": parametres,
            "responses": reponses,
            "security": [] if publique else [{"cookieAuth": []}],
        }
        if doc.corps:
            operation["requestBody"] = {"required": True, "content": {
                "application/json": {"schema": reference(doc.corps, "validation")}}}
        chemins.setdefault(chemin, {})[methode.lower()] = operation

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "API Réservation de salles (SAE R5A5, sujet A)",
            "version": "1.0.1",
            "description": (
                "Authentification par cookies httpOnly : `POST /api/auth/connexion` dépose "
                "`access_token_cookie` (15 min) et `refresh_token_cookie` (12 h). "
                "Toute requête qui modifie des données doit recopier le cookie "
                "`csrf_access_token` dans l'en-tête `X-CSRF-TOKEN`. Toutes les routes "
                "exigent une session sauf celles marquées sans sécurité.\n\n"
                "Les dates sans fuseau sont interprétées à l'heure de Paris. Les collections "
                "qui grandissent sont paginées (`page`, `taille`, réponse "
                "`{elements, total, page, taille}`).\n\n"
                "Limites : 300 requêtes/min par adresse IP (10/min pour la connexion), "
                "corps de 64 Kio au plus ; au-delà, 429 avec `Retry-After` (413 pour la "
                "taille). Évolution : ajouts sans préavis, changement incompatible livré avec "
                "le front (voir docs/api.md)."
            ),
        },
        "servers": [{"url": "/"}],
        "paths": chemins,
        "components": {
            "schemas": definitions,
            "securitySchemes": {"cookieAuth": {
                "type": "apiKey", "in": "cookie", "name": "access_token_cookie"}},
        },
    }


# ------------------------------------------------------------ Swagger UI
_CDN = f"https://cdn.jsdelivr.net/npm/swagger-ui-dist@{VERSION_SWAGGER_UI}"
_PAGE = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Documentation de l'API - Réservation de salles</title>
  <link rel="stylesheet" href="{_CDN}/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="{_CDN}/swagger-ui-bundle.js"></script>
  <script src="/api/docs/initialisation.js"></script>
</body>
</html>"""

# Les essais depuis Swagger UI utilisent la session ouverte dans l'appli :
# on recopie le cookie CSRF dans l'en-tête attendu par l'API.
_INITIALISATION = """
function lireCookie(nom) {
  const trouve = document.cookie.split('; ').find((c) => c.startsWith(nom + '='));
  return trouve ? decodeURIComponent(trouve.split('=')[1]) : null;
}
window.ui = SwaggerUIBundle({
  url: '/api/openapi.json',
  dom_id: '#swagger-ui',
  requestInterceptor: (requete) => {
    if (requete.method && requete.method.toUpperCase() !== 'GET') {
      const rafraichissement = /\\/api\\/auth\\/(rafraichissement|deconnexion)/.test(requete.url);
      const jeton = lireCookie(rafraichissement ? 'csrf_refresh_token' : 'csrf_access_token');
      if (jeton) requete.headers['X-CSRF-TOKEN'] = jeton;
    }
    return requete;
  },
});
"""

_CSP_DOCUMENTATION = (
    "default-src 'none'; script-src 'self' https://cdn.jsdelivr.net; "
    "style-src 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://cdn.jsdelivr.net; connect-src 'self'; frame-ancestors 'none'"
)

bp_documentation = Blueprint("documentation", __name__, url_prefix="/api")


@bp_documentation.get("/openapi.json")
@route_publique
def document_openapi() -> Response:
    return jsonify(generer_openapi(current_app._get_current_object()))  # type: ignore[attr-defined]


@bp_documentation.get("/docs")
@route_publique
def swagger_ui() -> Response:
    return Response(_PAGE, mimetype="text/html",
                    headers={"Content-Security-Policy": _CSP_DOCUMENTATION})


@bp_documentation.get("/docs/initialisation.js")
@route_publique
def swagger_initialisation() -> Response:
    return Response(_INITIALISATION, mimetype="text/javascript",
                    headers={"Content-Security-Policy": _CSP_DOCUMENTATION})
