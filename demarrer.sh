#!/usr/bin/env bash
# Lance l'application de réservation de salles en une commande : ./demarrer.sh
#
# Au premier lancement, le script prépare tout ce qui manque : environnement
# Python et dépendances, fichier backend/.env (clé secrète générée), base de
# données (utilisateur, bases, schéma, jeu de démonstration), dépendances du
# front. Ensuite il démarre l'API (port 5000) et le front (port 5173), puis
# ouvre le navigateur. Ctrl+C arrête les deux.
#
# Les lancements suivants ne refont que ce qui a changé : les données de la
# base sont conservées (sauf avec --reinitialiser).
set -euo pipefail

RACINE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$RACINE/backend"
FRONTEND="$RACINE/frontend"
VENV="$BACKEND/.venv"
PY="$VENV/bin/python"
PORT_API=5000
PORT_FRONT=5173
URL="http://localhost:$PORT_FRONT"
URL_LOCALE_PAR_DEFAUT="localhost:5432/sae_salles"

LANCER_TESTS=0
REINITIALISER=0
OUVRIR_NAVIGATEUR=1

aide() {
  cat <<EOF
Usage : ./demarrer.sh [options]

  --tests            lance d'abord tous les tests (backend et front)
  --reinitialiser    remet la base dans l'état de démonstration (EFFACE les données)
  --sans-navigateur  n'ouvre pas le navigateur
  --aide             affiche cette aide

Prérequis : Python 3.11+ (avec venv), Node.js 20.19+ et npm, PostgreSQL installé
localement (Ubuntu : sudo apt install postgresql).
EOF
}

for argument in "$@"; do
  case "$argument" in
    --tests) LANCER_TESTS=1 ;;
    --reinitialiser) REINITIALISER=1 ;;
    --sans-navigateur) OUVRIR_NAVIGATEUR=0 ;;
    -h | --aide | --help) aide; exit 0 ;;
    *) echo "Option inconnue : $argument" >&2; aide >&2; exit 1 ;;
  esac
done

etape() { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
ok() { printf '    \033[32mok\033[0m %s\n' "$*"; }
echec() { printf '\n\033[1;31mÉchec : %s\033[0m\n' "$*" >&2; exit 1; }

port_occupe() {
  python3 - "$1" <<'EOF'
import socket
import sys

with socket.socket() as s:
    s.settimeout(0.3)
    sys.exit(0 if s.connect_ex(("127.0.0.1", int(sys.argv[1]))) == 0 else 1)
EOF
}

# ------------------------------------------------------------------ prérequis
etape "Prérequis"
command -v python3 >/dev/null || echec "python3 introuvable (Ubuntu : sudo apt install python3 python3-venv)."
python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))' ||
  echec "Python 3.11 ou plus est nécessaire (trouvé : $(python3 --version 2>&1))."
ok "$(python3 --version 2>&1)"
{ command -v node >/dev/null && command -v npm >/dev/null; } ||
  echec "Node.js et npm introuvables : installez Node.js 22 (voir README, « Problèmes fréquents »)."
node -e '
  const [majeure, mineure] = process.versions.node.split(".").map(Number);
  const ok = (majeure === 20 && mineure >= 19) || (majeure === 22 && mineure >= 12) || majeure >= 23;
  process.exit(ok ? 0 : 1);' ||
  echec "Node.js 20.19+ ou 22.12+ est nécessaire (trouvé : $(node --version))."
ok "Node.js $(node --version)"
for port in "$PORT_API" "$PORT_FRONT"; do
  if port_occupe "$port"; then
    echec "Le port $port est déjà utilisé : l'application tourne peut-être déjà dans un autre terminal (Ctrl+C pour l'arrêter)."
  fi
done

# ---------------------------------------------------------------- backend
etape "Environnement Python (backend/.venv)"
if [ -x "$PY" ] && ! "$PY" -m pip --version >/dev/null 2>&1; then
  rm -rf "$VENV" # venv incomplet (python3-venv absent lors d'une tentative précédente)
fi
if [ ! -x "$PY" ]; then
  python3 -m venv "$VENV" 2>/dev/null || {
    rm -rf "$VENV"
    echec "Impossible de créer l'environnement virtuel (Ubuntu : sudo apt install python3-venv)."
  }
  ok "environnement virtuel créé"
fi
EMPREINTE="$(cat "$BACKEND"/requirements*.txt | sha256sum | cut -d' ' -f1)"
if [ "$(cat "$VENV/.empreinte-dependances" 2>/dev/null || true)" != "$EMPREINTE" ]; then
  echo "    installation des dépendances Python (une minute la première fois)..."
  "$PY" -m pip install --quiet --disable-pip-version-check -r "$BACKEND/requirements-dev.txt" ||
    echec "Installation des dépendances Python impossible (connexion Internet ? voir le message ci-dessus)."
  echo "$EMPREINTE" >"$VENV/.empreinte-dependances"
fi
ok "dépendances Python à jour"

etape "Configuration (backend/.env)"
if [ ! -f "$BACKEND/.env" ]; then
  SECRET="$("$PY" -c 'import secrets; print(secrets.token_urlsafe(48))')"
  cat >"$BACKEND/.env" <<EOF
# Créé par demarrer.sh pour un poste de développement (ne pas committer).
APP_ENV=development
DATABASE_URL=postgresql+psycopg2://sae:sae@$URL_LOCALE_PAR_DEFAUT
TEST_DATABASE_URL=postgresql+psycopg2://sae:sae@${URL_LOCALE_PAR_DEFAUT}_test
SECRET_KEY=$SECRET
EOF
  ok "backend/.env créé (base locale sae/sae, clé secrète générée)"
else
  ok "backend/.env existant conservé"
fi

flask_cmd() { (cd "$BACKEND" && "$VENV/bin/flask" --app wsgi "$@"); }
initialiser_base() {
  if [ "$REINITIALISER" = 1 ]; then flask_cmd init-db; else flask_cmd init-db --si-vide; fi
}

creer_base_locale() {
  echo "    création de l'utilisateur « sae » et des bases (mot de passe sudo demandé)..."
  # systemctl sur Ubuntu ; service sous WSL quand systemd n'y est pas activé.
  sudo systemctl start postgresql 2>/dev/null || sudo service postgresql start 2>/dev/null || true
  (cd /tmp && sudo -u postgres psql -v ON_ERROR_STOP=1 -q) <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'sae') THEN
    CREATE ROLE sae LOGIN PASSWORD 'sae';
  END IF;
END
$$;
SELECT 'CREATE DATABASE sae_salles OWNER sae'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sae_salles')\gexec
SELECT 'CREATE DATABASE sae_salles_test OWNER sae'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'sae_salles_test')\gexec
SQL
}

etape "Base de données"
set +e
initialiser_base
code=$?
set -e
if [ "$code" -eq 2 ]; then
  grep -q "$URL_LOCALE_PAR_DEFAUT" "$BACKEND/.env" ||
    echec "Base injoignable : vérifiez DATABASE_URL dans backend/.env."
  if id postgres >/dev/null 2>&1 && command -v sudo >/dev/null; then
    creer_base_locale || echec "Création de la base impossible (PostgreSQL est-il installé ? sudo apt install postgresql)."
  else
    echec "PostgreSQL introuvable : installez-le (sudo apt install postgresql)."
  fi
  initialiser_base || echec "Initialisation de la base impossible (voir le message ci-dessus)."
elif [ "$code" -ne 0 ]; then
  echec "Initialisation de la base impossible (voir le message ci-dessus)."
fi
ok "base prête"

# ------------------------------------------------------------------ front
etape "Dépendances du front (frontend/node_modules)"
if [ ! -f "$FRONTEND/node_modules/.package-lock.json" ] ||
  [ "$FRONTEND/package.json" -nt "$FRONTEND/node_modules/.package-lock.json" ]; then
  (cd "$FRONTEND" && npm install --no-fund --no-audit) ||
    echec "npm install a échoué. Essayez : cd frontend && rm -rf node_modules package-lock.json, puis relancez."
fi
ok "dépendances du front à jour"

# ------------------------------------------------------------------ tests
if [ "$LANCER_TESTS" = 1 ]; then
  etape "Tests"
  (cd "$BACKEND" && "$VENV/bin/pytest") || echec "des tests backend échouent."
  (cd "$FRONTEND" && npm test --silent) || echec "des tests front échouent."
fi

# -------------------------------------------------------------- démarrage
etape "Démarrage"
PIDS=()
arreter() {
  trap - INT TERM EXIT
  printf '\nArrêt de l'"'"'application...\n'
  for pid in "${PIDS[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap arreter INT TERM EXIT

(cd "$BACKEND" && exec "$VENV/bin/flask" --app wsgi run --port "$PORT_API" --no-reload) &
PIDS+=("$!")
for _ in $(seq 1 40); do
  kill -0 "${PIDS[0]}" 2>/dev/null || echec "l'API s'est arrêtée au démarrage (voir les messages ci-dessus)."
  "$PY" - "$PORT_API" <<'EOF' && break
import sys
import urllib.error
import urllib.request

try:
    urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/api/sante", timeout=1)
except urllib.error.HTTPError:
    pass  # 503 : l'API répond, la base est signalée indisponible
except OSError:
    sys.exit(1)
EOF
  sleep 0.5
done

(cd "$FRONTEND" && exec ./node_modules/.bin/vite --port "$PORT_FRONT" --strictPort --clearScreen false) &
PIDS+=("$!")
sleep 2

cat <<EOF

  Application prête : $URL
  Documentation de l'API : $URL/api/docs

  Comptes de démonstration (mot de passe : motdepasse)
    etud@iut.fr   étudiant
    prof@iut.fr   enseignant
    gest@iut.fr   gestionnaire

  Ctrl+C pour arrêter.

EOF
if [ "$OUVRIR_NAVIGATEUR" = 1 ]; then
  if grep -qi microsoft /proc/version 2>/dev/null && command -v explorer.exe >/dev/null; then
    explorer.exe "$URL" >/dev/null 2>&1 || true # WSL : navigateur par défaut de Windows
  elif [ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ] && command -v xdg-open >/dev/null; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  fi
fi

# Dès que l'API ou le front s'arrête, on arrête l'autre.
wait -n
