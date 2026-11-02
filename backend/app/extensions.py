"""Instances partagées des extensions Flask (initialisées dans create_app)."""
from flask_jwt_extended import JWTManager
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase

from .temps_reel import DiffuseurEvenements


class Base(DeclarativeBase):
    """Base déclarative SQLAlchemy 2.x (annotations Mapped[...])."""


db = SQLAlchemy(model_class=Base)
jwt = JWTManager()
diffuseur = DiffuseurEvenements()
