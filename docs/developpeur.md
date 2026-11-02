# Documentation développeur

Installation et lancement : voir le [README](../README.md). Ce document explique comment le
code est organisé et comment le faire évoluer sans casser les règles du sujet.

## Vue d'ensemble

```
Navigateur (React)                         API Flask                              PostgreSQL
pages ─► services ─► api/client.ts ──HTTP──► routes (contrôleurs)                  schema.sql
  ▲                        │  cookies JWT     │ DTO pydantic, rôle                 contraintes EXCLUDE
  │                        │  + X-CSRF-TOKEN  ▼                                    déclencheur
  └── usePlanning ◄──SSE── /api/evenements   services (cas d'usage) ─► ports ◄── dépôts SQLAlchemy
                                              │ règles du domaine (pures)
                                              └─► diffuseur temps réel (après commit)
```

Schémas (contexte, conteneurs, modèle de données, séquence d'une réservation) :
[architecture.md](architecture.md).

## Backend

### Couches

| Couche | Dossier | Rôle | Ne fait jamais |
|---|---|---|---|
| Contrôleur | `app/api/routes/` | lire et valider les DTO, appeler un service (`services()`), choisir le code HTTP | de logique métier, de SQL |
| DTO / mappers | `app/api/dto.py`, `mappers.py` | contrat JSON de l'API, projection explicite entités -> DTO | |
| Service (application) | `app/services/` | cas d'usage : enchaîne règles et dépôts, gère la transaction, journalise l'événement métier, publie l'événement temps réel ; dépend uniquement des contrats de `ports.py` | importer Flask, SQLAlchemy ou `logging`, renvoyer un code HTTP |
| Domaine | `app/domaine/` | règles pures (créneaux, limite étudiant, description, mots de passe, rôles), erreurs métier | dépendre de quoi que ce soit d'autre |
| Persistance | `app/persistance/` | modèles SQLAlchemy, dépôts (toutes les requêtes), transaction, traduction des violations de contraintes en erreurs métier | |
| Temps réel | `app/temps_reel.py` | diffusion SSE, reprise après coupure | |
| Composition | `app/composition.py` | seul endroit qui câble les services avec leurs implémentations, au démarrage ; y sont aussi définis le journal (`logging`), l'horloge et le hachage des mots de passe | |

Les dépendances vont vers l'intérieur : les contrôleurs connaissent les services, les
services ne connaissent que le domaine et les **ports** (`services/ports.py`, des `Protocol`
Python). Chaque service reçoit ses dépôts, sa transaction, son horloge, son journal et sa
diffusion **par son constructeur** ; `composition.py` les câble au démarrage. En test, les
mêmes services reçoivent des dépôts en mémoire (`tests/unitaires/faux.py`) : les règles
métier se testent sans base ni serveur.

Les services lèvent des erreurs métier (`DonneesInvalides`, `AccesRefuse`, `Conflit`...).
`app/api/erreurs.py` les traduit en réponses `{"code", "message", "details"}` avec le bon
statut (`HTTPStatus`, jamais de nombre en dur).

Choix assumé : pas d'entités de domaine dupliquées. Les ports décrivent la forme des objets
(`Protocol`) ; en production, les dépôts renvoient directement les modèles SQLAlchemy, qui
ont cette forme. On évite ainsi une couche de conversion entité <-> modèle sans rien coûter
à la testabilité.

### Ajouter une route

1. DTO d'entrée et de sortie dans `api/dto.py` (`extra="forbid"` hérité de `Entree`).
2. Règle métier pure dans `domaine/` si elle est réutilisable ou délicate, avec son test
   dans `tests/unitaires/`.
3. Cas d'usage : une méthode d'un service de `services/` (nouvelle dépendance = nouveau
   paramètre du constructeur, typé par un port, câblé dans `composition.py`). Vérifier les
   droits métier (`exiger_gestionnaire`, titulaire...) après avoir chargé la ressource,
   appeler les dépôts, `self._socle.transaction.valider()`, puis
   `self._socle.journal.evenement("nom.stable", ...)` et la publication temps réel **après**
   le commit. Test du cas d'usage dans `tests/unitaires/test_services.py`, avec les faux.
4. Route dans `api/routes/`, décorée dans cet ordre :
   ```python
   @bp.post("/chemin")
   @documenter("Résumé", tags=(...), corps=dto.X, reponses={201: dto.Y})  # OpenAPI
   @roles_requis(Role.GESTIONNAIRE)        # facultatif : sans lui, toute session suffit
   def vue():
       return repondre(..., services().mon_service.ma_methode(acteur_courant(), ...))
   ```
   La session est exigée par défaut ; une route publique se déclare avec `@route_publique`
   (et s'ajoute à `ROUTES_PUBLIQUES` dans les tests).
5. Test de droits dans `tests/droits/` : le refus d'abord (401 sans session, 403 avec un
   rôle insuffisant), puis le cas autorisé.

### Authentification et autorisation

- Connexion : `POST /api/auth/connexion` crée une ligne `session_utilisateur` et dépose deux
  cookies httpOnly : jeton d'accès (15 min, chemin `/api/`) et jeton de rafraîchissement
  (12 h, chemin `/api/auth/`). Les deux portent l'identifiant de session (`sid`).
- Chaque requête : flask-jwt-extended vérifie la signature, l'expiration, puis
  `token_in_blocklist_loader` vérifie que la session n'est pas révoquée. Le compte (et donc
  le **rôle**) est relu en base : un changement de rôle s'applique immédiatement.
- CSRF : pour POST/PATCH/DELETE, l'en-tête `X-CSRF-TOKEN` doit recopier le cookie
  `csrf_access_token` (`csrf_refresh_token` pour rafraîchir et se déconnecter).
- Force brute : table `verrou_connexion` ; après 3 échecs consécutifs sur une adresse, délai
  qui double à chaque échec (1 s, 2 s, 4 s… 15 min au plus), que l'adresse existe ou non.
  Limitation de débit par IP en plus (`app/limitation.py`, réglages `LIMITE*` de `config.py`).
- Refus par défaut : `exiger_authentification` (dans `api/securite.py`) refuse toute route
  sans session, sauf `@route_publique`. Une nouvelle route publique doit être ajoutée à
  `ROUTES_PUBLIQUES` dans `tests/droits/test_authentification.py`, sinon le test échoue.
- Contrôle d'accès en deux niveaux : décorateur `roles_requis` sur la route, et revérification
  dans le service (titulaire ou gestionnaire, rôles qui réservent...).

### Règles métier et concurrence

- Grille horaire : réservations et fermetures à heure pleine, dans le fuseau `Europe/Paris`
  (jamais celui du serveur). Une date sans fuseau reçue par l'API est une heure de Paris.
- Non-chevauchement (A-03) garanti par PostgreSQL (`EXCLUDE USING gist`), y compris pour deux
  requêtes simultanées. Une personne ne peut pas non plus occuper deux salles à la fois.
- Limite étudiant (A-09) : `domaine/creneaux.py::verifier_limite_etudiant` cumule les
  réservations qui se touchent ; la ligne de l'utilisateur est verrouillée (`FOR UPDATE`) pour
  que deux requêtes parallèles ne contournent pas la règle.
- Verrous toujours pris dans le même ordre (utilisateur puis salle) pour éviter les interblocages.
- Historique (A-08) : une réservation ne se supprime pas ; le déclencheur
  `reservation_historique_immuable` n'autorise que l'annulation d'une réservation active.

### Temps réel

`app/temps_reel.py` : un `DiffuseurEvenements` en mémoire, une file par client SSE et un
historique des 500 derniers événements. Les services publient (par `PublicationPlanning`)
`{"type": "planning", "salle_id", "jours"}` ou `{"type": "salles"}` après le commit ; chaque
événement porte un `id:`. À la reconnexion, `Last-Event-ID` (ou `?depuis=`) permet de
rejouer les événements manqués ; sinon le message `connecte` indique `reprise: impossible`
et le client recharge. Pulsation toutes les 15 s, fermeture à l'expiration du jeton
d'accès, une ligne de journal à l'ouverture et à la fermeture de chaque flux. Détails et
limites : [fiche 02](adr/02-temps-reel.md).

### Journalisation

`app/journalisation.py` : une ligne JSON par requête (`sae.requetes`, message
`requete.traitee`) et par événement métier (`sae.metier`, `sae.securite`, `sae.temps_reel`),
dans la console et dans `backend/logs/api.log` (180 jours) et `backend/logs/erreurs.log`
(ERROR, 365 jours), sauf si `LOG_DIR` est vide (console seule). Niveau : INFO (2xx/3xx),
WARNING (4xx), ERROR (5xx ; la pile d'appels part sur une ligne `exception.non_geree` reliée
par `id_requete`). Chaque réponse porte un en-tête `X-Request-ID`. Liste des champs : [fiche 03](adr/03-journalisation.md).
Exemples : `jq 'select(.statut >= 400)' logs/api.log`,
`jq -s 'group_by(.route) | map({route: .[0].route, moyenne_ms: (map(.duree_ms) | add / length)})' logs/api.log`.

### Base de données

`db/schema.sql` est la source de vérité (aucun `create_all`). Pour modifier le modèle :
changer le SQL, puis les modèles de `persistance/modeles.py`, puis relancer
`flask --app wsgi init-db` (en développement : la commande efface tout).

### Qualité

- `ruff check .` (PEP 8, imports triés, bugs courants) — configuration dans `pyproject.toml`.
- Nommage métier en français, cohérent entre base, API et interface (salle, créneau,
  réservation, fermeture, gestionnaire).
- Commentaires réservés au « pourquoi » (règle de sécurité, choix d'algorithme, regex).

## Frontend

| Dossier | Rôle |
|---|---|
| `api/client.ts` | seul point d'accès réseau : cookies, en-tête CSRF, rafraîchissement de session sur 401, erreurs typées (`ErreurApi`) |
| `api/dto.ts`, `api/mappers.ts` | forme des données de l'API et conversion vers les modèles |
| `models/` | modèles internes (camelCase, `Date`), libellés |
| `services/` | une fonction par appel d'API ; `tempsReel.ts` gère le flux SSE (reconnexion, resynchronisation) |
| `auth/` | contexte d'authentification, `RouteProtegee` / `RouteInvite` (gardes), `Autorise` (affichage par rôle), table des accès |
| `hooks/usePlanning.ts` | planning d'un jour + mises à jour temps réel, sans état périmé |
| `pages/` | composants « intelligents » : chargent les données, appellent les services |
| `components/` | composants de présentation (grille, panneau, éditeur...) : props en entrée, événements en sortie |
| `utils/` | fonctions pures testées (`npm test`) : dates de l'IUT, Markdown, grille |

Règles :

- la description n'est jamais injectée en HTML : `RenduDescription` construit les éléments
  React à partir de l'arbre Markdown (ESLint interdit `dangerouslySetInnerHTML`) ;
- les filtres et le jour affiché sont dans l'URL (partage de lien, actualisation) ;
- les gardes de routes ne sont qu'un confort : l'API refuse de toute façon (401/403).

## Organisation Git

Git Flow allégé, comme demandé en cours : `main` (versions livrées), `develop` (intégration),
`feature/<sujet>`, `fix/<sujet>`, `refactor/<sujet>`. Une fusion vers `develop` passe par une
relecture et par `pytest`, `npm test`, `npm run lint`.
