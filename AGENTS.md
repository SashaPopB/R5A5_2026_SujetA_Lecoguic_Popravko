# Conventions du projet (pour les assistants de code et les nouveaux arrivants)

Application de réservation de salles (SAE R5A5, sujet A). Front React + TypeScript, API
Flask, PostgreSQL. Tout le code, les commentaires et les messages sont en **français**.

## Où va le code

- `backend/app/domaine/` : règles métier pures. Aucun import de Flask, SQLAlchemy, logging.
- `backend/app/services/` : cas d'usage, une classe par domaine fonctionnel. Dépendances
  reçues par le constructeur, typées par `services/ports.py`. Jamais de code HTTP, de SQL ni
  de `logging` : journaliser avec `self._socle.journal.evenement("nom.stable", champ=...)`.
- `backend/app/persistance/` : seul endroit avec du SQL (dépôts `...Sql`).
- `backend/app/api/routes/` : contrôleurs minces (DTO -> service -> mapper -> `repondre`).
- `backend/app/composition.py` : câblage. Une nouvelle dépendance se déclare ici.
- `frontend/src/` : `api/` (client HTTP, DTO, mappers), `services/` (appels), `hooks/`,
  `utils/` (fonctions pures testées), `components/` (présentation), `pages/` (orchestration).

## Règles à ne pas casser

- Toute route exige une session ; une exception se déclare avec `@route_publique` et
  s'ajoute à `ROUTES_PUBLIQUES` (`tests/droits/test_authentification.py`).
- Rôle vérifié sur la route (`@roles_requis`), propriété de la ressource dans le service,
  après l'avoir chargée.
- Réponses construites par les mappers (projection explicite), jamais l'entité brute.
- Publier un événement temps réel **après** le commit, sans donnée personnelle.
- Jamais de mot de passe, jeton, adresse e-mail ou corps de requête dans les journaux.
- Jamais de `dangerouslySetInnerHTML` : la description passe par `RenduDescription`.
- Horodatages : toujours avec fuseau, heure de Paris (`Europe/Paris`).
- Pas de valeur magique : nommer la constante ; pas de booléen qui choisit entre deux
  comportements (faire deux fonctions).

## Commandes

```bash
cd backend && ruff check . && pytest            # lint, tests unitaires + droits
cd frontend && npm run lint && npm test && npm run build
```

Tout changement de règle d'accès s'accompagne du test qui montre le **refus**.
Documentation à tenir à jour : `docs/api.md` (contrat), `docs/adr/` (une fiche par
décision, nouvelle fiche plutôt que réécriture), `docs/developpeur.md`.
