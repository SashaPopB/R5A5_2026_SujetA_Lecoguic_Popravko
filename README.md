# SAE R5A5 — Sujet A · Réservation de salles

Outil web du secrétariat de l'IUT : état des salles de travail à jour (en temps réel),
réservation par les étudiants et les enseignants, administration des salles par le
gestionnaire et trace complète de qui a réservé ou annulé, et quand. L'API est appelée
uniquement par le front de l'application ; elle ne dépend que de PostgreSQL.

Front **React + TypeScript** (Vite) · API **Flask** · base **PostgreSQL**.

| Document | Contenu |
|---|---|
| [docs/developpeur.md](docs/developpeur.md) | Couches, conventions, ajouter une fonctionnalité, tests, journaux |
| [docs/architecture.md](docs/architecture.md) | Schémas : contexte, conteneurs, modèle de données, séquence d'une réservation |
| [docs/api.md](docs/api.md) | Authentification, erreurs, pagination, limites, versions, routes, temps réel |
| `/api/docs` (Swagger UI) | Documentation interactive générée depuis le code (source unique : les DTO) |
| [docs/adr/](docs/adr/) | Fiches de décision : BDD, temps réel, journalisation (obligatoires), cookies, description riche |
| [docs/deploiement.md](docs/deploiement.md) | Mise en production, nginx, secrets, incident, retour arrière |
| [AGENTS.md](AGENTS.md) | Conventions du projet, lues par les assistants de code |

---

## Démarrage en une commande

```bash
./demarrer.sh
```

Le script prépare ce qui manque (environnement Python et dépendances, `backend/.env` avec
une clé générée, utilisateur et bases PostgreSQL, schéma et données de démonstration,
dépendances du front), démarre l'API et le front, puis ouvre <http://localhost:5173>.
Ctrl+C arrête tout. Les lancements suivants conservent les données.

| Option | Effet |
|---|---|
| `--tests` | lance d'abord tous les tests (backend et front) |
| `--reinitialiser` | remet la base dans l'état de démonstration (efface les données) |
| `--sans-navigateur` | n'ouvre pas le navigateur |

Il faut Python 3.11+, Node.js 20.19+ et PostgreSQL : voir les
prérequis ci-dessous. Sur Windows : voir [Installation sur Windows (WSL)](#installation-sur-windows-wsl).

## Prérequis

| Outil | Version | Remarque |
|---|---|---|
| Python | 3.11 à 3.14 | avec `venv` (Ubuntu : `sudo apt install python3-venv`) |
| Node.js | 20.19 ou plus (22 conseillé) | vérifier avec `node --version` (exigé par Vite 8) |
| PostgreSQL | 13 ou plus (16 conseillé) | Ubuntu : `sudo apt install postgresql` |
| Windows | pas en dessous de 10 | dans WSL 2 avec Ubuntu, voir ci-dessous |

Toutes les commandes se lancent **depuis le dossier du projet** (celui qui contient ce
README) : `backend/` pour Python, `frontend/` pour npm. Les dépendances Python s'installent
dans un environnement virtuel, pas avec `apt`.

## Installation sur Windows (WSL)

Le projet tourne dans WSL 2, le Linux intégré à Windows ; l'application s'affiche dans le
navigateur de Windows.

1. **Installer WSL et Ubuntu.** Dans PowerShell ouvert en administrateur :

   ```powershell
   wsl --install
   ```

   Redémarrer, ouvrir « Ubuntu » depuis le menu Démarrer et choisir un nom d'utilisateur et
   un mot de passe Linux (`sudo` les demandera). Si WSL est déjà installé sans Ubuntu :
   `wsl --install -d Ubuntu`.

2. **Installer les outils**, dans le terminal Ubuntu :

   ```bash
   sudo apt update
   sudo apt install -y python3 python3-venv postgresql git unzip curl
   ```

   Puis Node.js 22 avec nvm (la version fournie par `apt` est souvent trop ancienne) :

   ```bash
   curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
   source ~/.bashrc
   nvm install 22
   node --version   # 22.x
   ```

3. **Récupérer le projet dans le dossier Linux** (`~`), pas sous `/mnt/c/...` : depuis
   Windows, npm y est très lent et le script peut perdre ses droits d'exécution.

   ```bash
   cd ~
   git clone https://github.com/DUT-Info-Montreuil/R5A5_2026_SujetA_Lecoguic_Popravko.git
   cd R5A5_2026_SujetA_Lecoguic_Popravko
   ```

   Avec une archive zip téléchargée sous Windows :
   `cp /mnt/c/Users/<nom>/Downloads/<archive>.zip ~ && cd ~ && unzip <archive>.zip`, puis
   aller dans le dossier qui contient ce README.

4. **Lancer** :

   ```bash
   ./demarrer.sh
   ```

   Au premier lancement, le mot de passe Linux est demandé pour démarrer PostgreSQL et créer
   l'utilisateur `sae` et les bases. L'application s'ouvre dans le navigateur de Windows ;
   sinon, ouvrir <http://localhost:5173>.

5. **VS Code** (facultatif) : installer l'extension « WSL » de Microsoft, puis taper
   `code .` dans le dossier du projet, depuis Ubuntu. L'éditeur travaille alors
   directement sur les fichiers Linux.

## Installation pas à pas (Linux ou WSL)

### 1. Base de données

`./demarrer.sh` fait cette étape tout seul. À la main : dans `psql` (ou le Query Tool de
pgAdmin) connecté en administrateur, sur Ubuntu `sudo -u postgres psql` :

```sql
CREATE USER sae WITH PASSWORD 'sae';
CREATE DATABASE sae_salles OWNER sae;
CREATE DATABASE sae_salles_test OWNER sae;
```

L'extension `btree_gist` (utilisée par les contraintes anti-chevauchement) est créée par le
schéma ; depuis PostgreSQL 13 le propriétaire de la base a le droit de le faire.

### 2. API (dossier `backend/`)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate            # à refaire dans chaque nouveau terminal ; Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt  # Flask, SQLAlchemy, pytest... dans .venv
cp .env.example .env                 # puis remplir les valeurs (voir ci-dessous)
flask --app wsgi init-db             # schéma + jeu de démonstration (EFFACE la base)
flask --app wsgi run --debug         # http://localhost:5000
```

Valeurs de `.env` pour un poste de développement :

```dotenv
APP_ENV=development
DATABASE_URL=postgresql+psycopg2://sae:sae@localhost:5432/sae_salles
SECRET_KEY=<sortie de : python -c "import secrets; print(secrets.token_urlsafe(48))">
TEST_DATABASE_URL=postgresql+psycopg2://sae:sae@localhost:5432/sae_salles_test
```

L'API refuse de démarrer sans `DATABASE_URL` ou avec un `SECRET_KEY` de moins de 32 caractères.
Sans pgAdmin ni Flask, le schéma s'applique aussi à la main : `psql -f db/schema.sql` puis
`psql -f db/seed.sql`.

### 3. Frontend (dossier `frontend/`)

```bash
cd frontend
node --version                       # 20.19 ou plus (sinon : voir « Problèmes fréquents »)
npm install
npm run dev                          # http://localhost:5173
```

Vite relaie `/api` vers le port 5000 : le navigateur voit le front et l'API sur la même
origine (cookies `SameSite=Strict`, pas de CORS à configurer, le flux temps réel passe aussi).

### Comptes de démonstration (mot de passe : `motdepasse`)

| Adresse | Rôle | Peut |
|---|---|---|
| `etud@iut.fr` (Étudiant) | étudiant | réserver (2 h d'affilée au plus), annuler ses réservations |
| `prof@iut.fr` (Professeur) | enseignant | réserver sans limite de durée, annuler ses réservations |
| `gest@iut.fr` (Gestionnaire) | gestionnaire | gérer salles et créneaux, annuler toute réservation, historique, export CSV, rôles |

Salles de démonstration : D101, D102, D103, D201, D202 (bâtiment D) et B114 (bâtiment B).

L'inscription en ligne crée toujours un compte **étudiant** ; le gestionnaire attribue les
autres rôles (page *Comptes*).

---

## Tests

```bash
cd backend && pytest          # unitaires (règles et cas d'usage, sans base) + droits (base TEST_DATABASE_URL)
cd frontend && npm test       # Markdown, dates, construction de la grille
cd frontend && npm run lint   # ESLint (dont l'interdiction de dangerouslySetInnerHTML)
cd frontend && npm run build  # vérification TypeScript + build de production
cd backend && ruff check .    # PEP 8, imports, bugs courants
```

Les **tests de droits** (`backend/tests/droits/`) vérifient pour chaque règle d'accès
qu'un utilisateur non autorisé est refusé (401/403), pas seulement que l'utilisateur
autorisé passe ; l'un d'eux parcourt **toutes** les routes déclarées et exige un 401 sans
session, sauf pour la liste blanche des routes publiques. Ils tournent contre une vraie base PostgreSQL (vidée à chaque test) : si
elle est injoignable, pytest les marque « ignorés » en indiquant pourquoi.

## Documentation de l'API

- Swagger UI : <http://localhost:5000/api/docs> (ou <http://localhost:5173/api/docs>) ;
  les essais utilisent la session ouverte dans l'application.
- Document OpenAPI brut : `/api/openapi.json`.
- Vue d'ensemble rédigée : [docs/api.md](docs/api.md).

### Problèmes fréquents

| Message | Cause | Solution |
|---|---|---|
| `La commande « pytest » n'a pas été trouvée` ou `No module named 'flask'` | environnement virtuel absent ou pas activé | dans `backend/` : `source .venv/bin/activate` puis `pip install -r requirements-dev.txt` (ne pas installer pytest avec `apt`) |
| `ensurepip is not available` à la création du venv | paquet venv absent (Ubuntu) | `sudo apt install python3-venv` |
| `npm ERR! enoent ... package.json` | commande lancée hors de `frontend/` | `cd frontend` |
| `npm ERR! ERESOLVE could not resolve` (vite / @vitejs/plugin-react) | `node_modules` ou `package-lock.json` d'une autre version, souvent après `npm audit fix --force` | dans `frontend/` : `rm -rf node_modules package-lock.json` puis `npm install` ; ne pas lancer `npm audit fix --force` (il change de version majeure sans vérifier la compatibilité) |
| `Unknown file extension ".ts"` avec `npm test` | ancien `package.json` (tests lancés avec `node` seul, que Node d'Ubuntu ne sait pas faire) | `package.json` à jour : les tests passent par `tsx` |
| `vite` refuse de démarrer, version de Node trop ancienne | Node.js antérieur à 20.19 | installer Node 22 : `curl -fsSL https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh \| bash`, rouvrir le terminal, `nvm install 22` |
| tests de droits « ignorés : base de test injoignable » | PostgreSQL arrêté ou `TEST_DATABASE_URL` absent de `backend/.env` | démarrer PostgreSQL, créer `sae_salles_test` (installation pas à pas, étape 1) |
| `password authentication failed for user "sae"` | utilisateur PostgreSQL non créé | installation pas à pas, étape 1 (Ubuntu : `sudo -u postgres psql`) |
| WSL : `/usr/bin/env: 'bash\r': No such file or directory` | fins de ligne Windows (fichier passé par un outil Windows) | `sed -i 's/\r$//' demarrer.sh` ; à l'avenir, cloner depuis Ubuntu |
| WSL : `Permission denied` sur `./demarrer.sh` | droit d'exécution perdu en copiant depuis Windows | `chmod +x demarrer.sh` |
| WSL : `npm install` très lent, modifications non prises en compte | projet rangé sous `/mnt/c/...` | déplacer le projet dans `~` (étape 3 de l'installation WSL) |
| WSL : PostgreSQL arrêté après un redémarrage | systemd non activé dans WSL | `sudo service postgresql start` (`./demarrer.sh` le fait tout seul) |
| WSL : <http://localhost:5173> ne répond pas depuis Windows | redirection de `localhost` désactivée | retirer `localhostForwarding=false` de `%UserProfile%\.wslconfig`, puis `wsl --shutdown` |

---

## Exigences du sujet A

| Exigence | Où | Testé par |
|---|---|---|
| A-01 état des salles aujourd'hui et jours suivants | `GET /api/planning?date=` · page Planning, sélecteur de jours | `test_reservations.py` |
| A-02 réserver un créneau libre avec une description mise en forme | `POST /api/reservations` · éditeur Markdown (gras, italique, listes, liens) rendu sans HTML | `test_a02_*`, `test_description.py`, `markdown.test.ts` |
| A-03 un créneau réservé n'est plus proposé | contrainte `EXCLUDE` PostgreSQL + grille | `test_a02_a03_*` |
| A-04 mise à jour sans recharger | flux SSE `GET /api/evenements` | `test_a04_*`, `test_temps_reel.py` |
| A-05 annuler ses réservations, et seulement les siennes | `PATCH /api/reservations/<id>` | `test_a05_*` |
| A-06 seul le gestionnaire annule celle d'un autre | idem | `test_a06_*` |
| A-07 ouvrir, fermer, retirer une salle ; ouvrir/fermer des créneaux ; horaires | `PATCH /api/salles/<id>`, `POST/DELETE /api/fermetures` · pages Salles et Planning | `test_a07_*` |
| A-08 qui a réservé ou annulé, et quand | `GET /api/reservations` (historique paginé) · page Suivi et historique | `test_a08_*` |
| A-09 étudiant : 2 h d'affilée au plus | règle `bloc_contigu` + verrou par utilisateur | `test_a09_*`, `test_creneaux.py` |
| A-10 export CSV d'une période | `GET /api/reservations/export?du=&au=` | `test_a10_*`, `test_export_csv.py` |

Hors périmètre retirés de la version précédente : matériel des salles (exclu par le sujet),
circuit de validation des demandes, quotas, réservations répétées (proches de la gestion
d'emploi du temps, exclue).

---

## Déploiement (résumé)

- `pip install -r requirements-prod.txt`, `APP_ENV=production` (défaut), `SECRET_KEY` fort,
  HTTPS obligatoire (cookies `Secure`, en-tête HSTS).
- **Un seul processus multi-threadé** : `gunicorn -w 1 -k gthread --threads 64 -b 127.0.0.1:5000 wsgi:app`.
  Le temps réel et la limitation de débit vivent en mémoire (voir [fiche 02](docs/adr/02-temps-reel.md)).
- nginx sert `frontend/dist` (`npm run build`) et relaie `/api` sur la **même origine**,
  sans mise en tampon pour `/api/evenements`. Configuration complète, rotation des secrets
  et retour arrière : [docs/deploiement.md](docs/deploiement.md).

## Structure

```
db/                  schema.sql (source de vérité) · seed.sql (démo)
backend/
  app/domaine/       règles métier pures (créneaux, description, mots de passe, erreurs)
  app/services/      cas d'usage (réserver, annuler, fermer...) et ports (contrats injectés)
  app/persistance/   modèles SQLAlchemy, dépôts (toutes les requêtes SQL), transaction
  app/api/           contrôleurs, DTO pydantic, mappers, sécurité JWT, OpenAPI
  app/composition.py câblage des services au démarrage (injection de dépendances) ; journal,
                     horloge, hachage des mots de passe
  app/               temps_reel.py (SSE) · journalisation.py · limitation.py · securite_http.py
  tests/             unitaires/ (sans base, dépôts en mémoire) · droits/ (PostgreSQL)
frontend/src/
  api/               client HTTP (CSRF, rafraîchissement de session), DTO, mappers
  models/ services/  modèles internes · appels à l'API · flux temps réel
  auth/              contexte d'authentification, gardes de routes
  pages/ components/ pages (logique) · composants de présentation
  utils/             dates, Markdown, construction de la grille (testés)
docs/                développeur, architecture, API, adr/ (fiches de décision), déploiement
```
