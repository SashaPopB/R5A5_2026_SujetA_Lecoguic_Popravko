"""Commande d'administration : flask --app wsgi init-db."""
import sys
from pathlib import Path

import click
from flask import Flask
from sqlalchemy.exc import OperationalError

from .extensions import db

# Code de sortie quand la base est injoignable : demarrer.sh propose alors de
# créer l'utilisateur et les bases.
CODE_BASE_INJOIGNABLE = 2

DOSSIER_SQL = Path(__file__).resolve().parents[2] / "db"


def _executer_fichier_sql(nom: str) -> None:
    sql = (DOSSIER_SQL / nom).read_text(encoding="utf-8")
    with db.engine.begin() as connexion:
        connexion.exec_driver_sql(sql)


def _schema_present() -> bool:
    with db.engine.connect() as connexion:
        return connexion.exec_driver_sql(
            "SELECT to_regclass('public.reservation')").scalar() is not None


def enregistrer_commandes(app: Flask) -> None:
    @app.cli.command("init-db")
    @click.option("--sans-demo", is_flag=True, help="Schéma seul, sans données de démonstration.")
    @click.option("--si-vide", is_flag=True,
                  help="Ne fait rien si le schéma existe déjà (aucune donnée effacée).")
    def init_db(sans_demo: bool, si_vide: bool) -> None:
        """(Re)crée le schéma et charge le jeu de démonstration. EFFACE TOUT,
        sauf avec --si-vide sur une base déjà initialisée."""
        try:
            if si_vide and _schema_present():
                click.echo("Base déjà initialisée : données conservées.")
                return
        except OperationalError as exc:
            click.echo(f"Base injoignable : {exc.orig}".strip(), err=True)
            sys.exit(CODE_BASE_INJOIGNABLE)
        _executer_fichier_sql("schema.sql")
        click.echo(f"Schéma appliqué ({DOSSIER_SQL / 'schema.sql'}).")
        if not sans_demo:
            _executer_fichier_sql("seed.sql")
            click.echo("Données de démonstration chargées (mot de passe : motdepasse).")
