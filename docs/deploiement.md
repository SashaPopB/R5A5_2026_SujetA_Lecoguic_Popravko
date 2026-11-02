# Déploiement et exploitation

Un seul serveur Linux : nginx devant, l'API Flask (gunicorn) derrière, PostgreSQL à côté.
Le passage à plusieurs serveurs est hors du périmètre du projet.

## 1. Installer

```bash
git clone <dépôt> && cd sae-reservation-salles
psql -U postgres -c "CREATE USER sae WITH PASSWORD '<mot de passe fort>'" \
                 -c "CREATE DATABASE sae_salles OWNER sae"

cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-prod.txt
cp .env.example .env    # puis renseigner DATABASE_URL, SECRET_KEY, NB_PROXYS_DE_CONFIANCE=1
flask --app wsgi init-db --sans-demo

cd ../frontend && npm install && npm run build  # produit frontend/dist (npm ci une fois package-lock.json versionné)
```

## 2. Lancer l'API

```bash
gunicorn -w 1 -k gthread --threads 64 --graceful-timeout 10 -b 127.0.0.1:5000 wsgi:app
```

- **Un seul processus** (`-w 1`) : le diffuseur temps réel, son historique de reprise et
  les compteurs de limitation de débit vivent en mémoire (fiche 02).
- **Des threads** : chaque flux SSE occupe un thread tant que l'onglet est ouvert ; 64 threads
  couvrent quelques dizaines d'utilisateurs simultanés et leurs requêtes ordinaires.
- `--graceful-timeout 10` : à l'arrêt, gunicorn cesse d'accepter des connexions et laisse
  10 s aux requêtes en cours ; les flux SSE coupés se reconnectent seuls (délai aléatoire
  de 2 à 5 s) et rejouent ou rechargent ce qu'ils ont manqué.
- Service systemd conseillé (`Restart=on-failure`), utilisateur sans privilège.

## 3. nginx

```nginx
server {
    listen 443 ssl http2;
    server_name salles.iut.example;
    ssl_certificate     /etc/letsencrypt/live/salles.iut.example/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/salles.iut.example/privkey.pem;
    server_tokens off;                      # ne pas annoncer la version de nginx

    root /srv/sae-reservation-salles/frontend/dist;
    location / { try_files $uri /index.html; }

    location /api/ {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;   # avec ID_REQUETE_ENTRANT_ACCEPTE=true
        proxy_hide_header Server;                    # pas d'empreinte de gunicorn
    }

    location = /api/evenements {                     # flux SSE
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;                         # chaque événement part tout de suite
        proxy_cache off;
        proxy_read_timeout 60s;                      # > pulsation de 15 s
        proxy_hide_header Server;
    }
}
server { listen 80; server_name salles.iut.example; return 301 https://$host$request_uri; }
```

`http2` lève la limite de six connexions par domaine du HTTP/1.1 (un flux SSE par onglet).
Avec ce proxy, régler `NB_PROXYS_DE_CONFIANCE=1` : l'API lit l'adresse du client dans
`X-Forwarded-For` (limitation de débit, journal des refus).

## 4. Vérifier avant d'ouvrir

- [ ] `APP_ENV` vide ou `production` : mode debug coupé, cookies `Secure`, HSTS.
- [ ] `curl -I https://…/api/sante` : 200, en-têtes `Strict-Transport-Security`,
      `X-Content-Type-Options`, `Content-Security-Policy`, pas d'en-tête `Server` détaillé.
- [ ] Chaque route appelée sans session répond 401 (`pytest tests/droits` sur la base de test).
- [ ] Tests et lint au vert : `./demarrer.sh --tests`, `cd backend && ruff check .`,
      `cd frontend && npm run lint`.
- [ ] Aucune vulnérabilité connue dans les dépendances : `pip install pip-audit` puis
      `pip-audit -r backend/requirements.txt -r backend/requirements-prod.txt`, et
      `npm audit --omit=dev` dans `frontend/`.
- [ ] Les journaux arrivent : `tail -f backend/logs/api.log | jq .`

## 5. Journaux et supervision

- `logs/api.log` (180 jours) et `logs/erreurs.log` (365 jours), rotation à minuit UTC ; accès
  réservé aux administrateurs (`chmod 640`, groupe dédié).
- Une sonde externe appelle `GET /api/sante` chaque minute (503 si la base est injoignable).
  L'absence de lignes n'est pas un signe de bonne santé : une API arrêtée n'écrit plus rien.
- À surveiller : hausse des `niveau=="ERROR"`, séries de 401/429 depuis une même `ip`,
  hausse des `flux.ferme` avec `motif=="erreur"` ou des reconnexions (`flux.ouvert` avec
  `reprise=="impossible"`).

## 6. Secrets : procédure de remplacement

| Secret | Où | Remplacer |
|---|---|---|
| `SECRET_KEY` (signature des jetons) | `backend/.env` | générer `python -c "import secrets; print(secrets.token_urlsafe(48))"`, remplacer, redémarrer : tous les jetons deviennent invalides, tout le monde est déconnecté |
| Mot de passe PostgreSQL | `DATABASE_URL` | `ALTER USER sae PASSWORD '…'`, mettre à jour `.env`, redémarrer |
| Certificat TLS | nginx | renouvellement automatique (certbot) |

En cas de fuite (secret commité, serveur compromis) : **1.** révoquer d'abord (remplacer la
valeur comme ci-dessus ; supprimer le fichier du dépôt ne suffit pas, l'historique le garde),
**2.** fermer toutes les sessions (`UPDATE session_utilisateur SET revoquee_le = now() WHERE
revoquee_le IS NULL;`), **3.** analyser les journaux sur la période (`utilisateur`, `ip` des
refus, routes appelées), **4.** nettoyer l'historique Git si besoin, **5.** écrire le
post-mortem (chronologie, cause, ce qui change).

## 7. Mettre à jour et revenir en arrière

```bash
git fetch && git checkout v1.0.1            # chaque livraison est une étiquette Git
pip install -r backend/requirements.txt -r backend/requirements-prod.txt
(cd frontend && npm install && npm run build)
sudo systemctl restart sae-api
```

Retour arrière en cinq minutes : `git checkout <étiquette précédente>`, mêmes commandes.
Le schéma est créé par `db/schema.sql` ; une évolution de schéma se livre avec son script de
migration et son script inverse, et une sauvegarde (`pg_dump -Fc sae_salles`) est faite
avant chaque mise à jour.
