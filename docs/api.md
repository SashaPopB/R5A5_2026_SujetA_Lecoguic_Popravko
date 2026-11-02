# Documentation de l'API

La référence complète (schémas de chaque requête et réponse) est générée depuis le code :
Swagger UI sur **`/api/docs`**, document OpenAPI 3.1 sur **`/api/openapi.json`**. Cette page
donne les règles communes et une vue d'ensemble.

## Conventions

- Préfixe : `/api`. Corps et réponses en JSON (`Content-Type: application/json`, sinon 415).
- Identifiants : UUID.
- Dates : `AAAA-MM-JJ`. Horodatages : ISO 8601 avec décalage, à l'heure de Paris
  (`2026-11-02T10:00:00+01:00`). Une heure envoyée sans décalage (`2026-11-02T10:00`) est
  une heure de Paris.
- Réservations et fermetures commencent et finissent à une heure pleine.
- Méthodes : GET ne modifie jamais rien ; POST crée (201), PATCH modifie partiellement (200),
  DELETE supprime (204). Ressources au pluriel, en minuscules ; l'utilisateur connecté est
  déduit de la session (`/api/moi/...`), jamais d'un identifiant dans l'URL.
- Toute collection qui peut grandir est **paginée côté serveur**, avec une taille par défaut :
  `?page=1&taille=20` -> `{"elements": [...], "total": 57, "page": 1, "taille": 20}`
  (historique gestionnaire et comptes : 50 par défaut, 200 au plus ; mes réservations : 20
  par défaut, 100 au plus). Tri fixe documenté sur chaque route (plus récentes d'abord pour
  l'historique). Les listes bornées par nature (bâtiments, salles) ne sont pas paginées.
- Champs inconnus dans un corps : refusés (400 `validation`). Seuls les champs listés dans
  la documentation d'une réponse en sortent (projection explicite, jamais l'entité brute).

## Limites d'usage

| Limite | Valeur | Dépassement |
|---|---|---|
| Requêtes par adresse IP, toute l'API | 300 par minute | 429 `trop_de_requetes` + `Retry-After` |
| Connexions par adresse IP | 10 par minute | idem |
| Inscriptions par adresse IP | 5 par 10 minutes | idem |
| Rafraîchissements de session / exports CSV par IP | 30 / 10 par minute | idem |
| Essais de connexion ratés sur un même compte | 3 libres, puis délai doublé à chaque échec (1 s… 15 min) | 429 `trop_de_tentatives` + `Retry-After` |
| Taille d'un corps de requête | 64 Kio | 413 `requete_trop_volumineuse` |
| Description d'une réservation | 2 000 caractères | 400 |
| Période d'un export CSV | 366 jours | 400 `periode_trop_longue` |
| Réservation : horizon / durée étudiant | 60 jours à l'avance / 2 h d'affilée | 400 / 403 |

`/api/sante` n'est jamais limitée (sondes de supervision).

## Version et évolution

API interne, consommée uniquement par le front livré avec elle : pas de numéro de version
dans l'URL, le contrat OpenAPI est versionné avec le code (`info.version`). Règle de
changement : on peut **ajouter** sans prévenir (route, champ de réponse, paramètre
facultatif) ; renommer ou supprimer un champ, rendre un paramètre obligatoire ou changer un
code d'erreur demande de livrer le front correspondant en même temps. Si un autre client
apparaît, ces changements passeront par un préfixe `/api/v2`.

## Choix des statuts 400 / 409 / 422

L'API n'utilise pas 422 : **400** pour toute donnée invalide (JSON illisible, champ manquant
ou mal typé, valeurs incohérentes entre elles comme une fin avant le début), **409** quand
la donnée est valide mais contredit l'état enregistré (créneau déjà pris, déjà annulée).
Le champ `code` distingue les cas plus finement que le statut.

## Authentification

1. `POST /api/auth/connexion` `{"email", "mot_de_passe"}` dépose les cookies httpOnly
   `access_token_cookie` (15 min) et `refresh_token_cookie` (12 h), plus les cookies lisibles
   `csrf_access_token` et `csrf_refresh_token`.
2. Toute requête POST, PATCH ou DELETE recopie `csrf_access_token` dans l'en-tête
   `X-CSRF-TOKEN`.
3. À l'expiration du jeton d'accès (401 `jeton_expire`), `POST /api/auth/rafraichissement`
   (en-tête `X-CSRF-TOKEN` = `csrf_refresh_token`) dépose un nouveau jeton d'accès.
4. `POST /api/auth/deconnexion` révoque la session côté serveur et efface les cookies.

Exemple avec curl :

```bash
curl -c cj -H 'Content-Type: application/json' \
     -d '{"email":"etud@iut.fr","mot_de_passe":"motdepasse"}' \
     http://localhost:5000/api/auth/connexion
CSRF=$(awk '$6=="csrf_access_token"{print $7}' cj)
curl -b cj -H 'Content-Type: application/json' -H "X-CSRF-TOKEN: $CSRF" \
     -d '{"salle_id":"<uuid>","debut":"2026-11-02T10:00","fin":"2026-11-02T12:00","description":"**Projet** SAE"}' \
     http://localhost:5000/api/reservations
```

## Erreurs

Toutes les erreurs ont la même forme :

```json
{"code": "creneau_deja_reserve", "message": "La salle D101 est déjà réservée sur ce créneau.", "details": null}
```

| Statut | Quand | Codes fréquents |
|---|---|---|
| 400 | données invalides | `validation` (détail par champ), `heure_non_pleine`, `creneau_passe`, `hors_horaires_salle`, `lien_non_autorise`, `periode_invalide`, `mot_de_passe_previsible` |
| 401 | pas de session, session expirée ou révoquée, jeton CSRF absent | `authentification_requise`, `jeton_expire`, `session_revoquee`, `csrf_invalide`, `identifiants_invalides` |
| 403 | connecté mais pas autorisé, ou requête venue d'une autre origine | `role_insuffisant`, `reservation_d_un_autre`, `limite_etudiant_depassee`, `role_sans_reservation`, `origine_refusee` |
| 404 | ressource inconnue | `salle_introuvable`, `reservation_introuvable`, `route_introuvable` |
| 409 | conflit avec l'état actuel | `creneau_deja_reserve`, `reservation_simultanee`, `creneau_ferme`, `salle_fermee`, `deja_annulee`, `reservation_terminee` |
| 413 | corps de plus de 64 Kio | `requete_trop_volumineuse` |
| 415 | corps qui n'est pas du JSON | `type_contenu_non_supporte` |
| 429 | trop de requêtes ou d'essais de connexion (en-tête `Retry-After`) | `trop_de_requetes`, `trop_de_tentatives` |
| 500 | bug : message générique, rien sur le code ; `details.id_requete` à transmettre pour le signalement | `erreur_interne` |

Toutes les routes exigent une session, sauf `inscription`, `connexion`, `rafraichissement`,
`deconnexion`, `sante` et la documentation : une route sans session répond 401.

## Routes

| Méthode | Route | Accès | Réponse |
|---|---|---|---|
| POST | `/api/auth/inscription` | public | 201 compte (toujours étudiant) |
| POST | `/api/auth/connexion` | public | 200 compte + cookies |
| POST | `/api/auth/rafraichissement` | jeton de rafraîchissement | 204 |
| POST | `/api/auth/deconnexion` | — | 204 |
| GET | `/api/auth/moi` | connecté | compte |
| GET | `/api/batiments` | connecté | liste |
| GET | `/api/salles?inclure_retirees=` | connecté (retirées : gestionnaire) | liste |
| POST | `/api/salles` | gestionnaire | 201 salle |
| PATCH | `/api/salles/{id}` | gestionnaire | salle + `reservations_annulees` |
| GET | `/api/planning?date=` | connecté | salles, réservations, fermetures du jour |
| POST | `/api/reservations` | étudiant, enseignant | 201 réservation |
| GET | `/api/reservations?salle_id&du&au&statut&recherche&page&taille` | gestionnaire | page (historique) |
| GET | `/api/reservations/export?du&au` | gestionnaire | fichier CSV |
| PATCH | `/api/reservations/{id}` `{"statut":"annulee","motif"?}` | titulaire, gestionnaire | réservation annulée |
| GET | `/api/moi/reservations?periode=a_venir\|passees&page&taille` | connecté | page |
| POST | `/api/fermetures` | gestionnaire | 201 fermeture + `reservations_annulees` |
| DELETE | `/api/fermetures/{id}` | gestionnaire | 204 |
| GET | `/api/utilisateurs?recherche&page&taille` | gestionnaire | page |
| PATCH | `/api/utilisateurs/{id}` `{"role"}` | gestionnaire (pas sur soi) | compte |
| GET | `/api/evenements` | connecté | flux `text/event-stream` |
| GET | `/api/sante` | public | `{"statut","base_de_donnees"}` (503 si la base est injoignable) |

Dans le planning, `titulaire` et `description` valent `null` sauf pour le titulaire et le
gestionnaire : les autres voient seulement que le créneau est pris.

## Temps réel

`GET /api/evenements` (à ouvrir avec `new EventSource("/api/evenements")`, le cookie suffit) :

```
retry: 3412

event: connecte
data: {"type":"connecte","reprise":"initiale"}

id: 18a3f2c9b1d.12
event: planning
data: {"type":"planning","salle_id":"…","jours":["2026-11-02"]}

: pulsation
```

- `planning` : une réservation, une annulation ou une fermeture touche ces jours ;
  `{"type":"salles"}` : une salle a changé (état, horaires) ; `{"type":"resynchronisation"}` :
  le client a pris du retard et doit tout recharger.
- Les événements ne contiennent aucune donnée personnelle : le client recharge
  `GET /api/planning`, qui applique les règles de visibilité.
- Chaque événement a un `id:`. À la reconnexion, le navigateur renvoie l'en-tête
  `Last-Event-ID` ; un client qui rouvre lui-même le flux passe `?depuis=<id>`. Le message
  `connecte` indique alors `reprise: "complete"` (les événements manqués suivent
  immédiatement) ou `"impossible"` (trop anciens, ou serveur redémarré : recharger le
  planning). Premier abonnement : `"initiale"`.
- Le flux se ferme à l'expiration du jeton d'accès (15 min) ; le client rafraîchit sa
  session et se reconnecte. Délai de reconnexion conseillé (`retry`) tiré entre 2 et 5 s.
- Requête venue d'une autre origine (en-tête `Origin` inconnu) : 403 `origine_refusee`.
