"""Point d'entrée WSGI.

Développement : flask --app wsgi run --debug
Production    : gunicorn -w 1 -k gthread --threads 64 -b 127.0.0.1:5000 wsgi:app
                (un seul processus : le temps réel est diffusé en mémoire,
                voir docs/adr/02-temps-reel.md)
"""
from app import create_app

app = create_app()
