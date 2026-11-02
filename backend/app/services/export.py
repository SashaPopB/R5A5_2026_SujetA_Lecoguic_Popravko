"""Export CSV des réservations d'une période (A-10)."""
import csv
import io
from collections.abc import Iterable
from dataclasses import astuple, dataclass, fields
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from .ports import Reservation

# Une cellule qui commence par un de ces caractères serait interprétée comme
# une formule par Excel ou LibreOffice (injection de formule) : on la
# préfixe d'une apostrophe, qui force l'affichage en texte.
_DEBUTS_DE_FORMULE = ("=", "+", "-", "@", "\t", "\r")

ENTETES = {
    "reference": "Référence",
    "salle": "Salle",
    "batiment": "Bâtiment",
    "date": "Date",
    "debut": "Début",
    "fin": "Fin",
    "titulaire": "Réservé par",
    "email": "E-mail",
    "role": "Rôle",
    "description": "Description",
    "statut": "Statut",
    "cree_le": "Réservé le",
    "annulee_le": "Annulé le",
    "annulee_par": "Annulé par",
    "motif_annulation": "Motif d'annulation",
}


@dataclass(frozen=True)
class LigneExport:
    reference: str
    salle: str
    batiment: str
    date: str
    debut: str
    fin: str
    titulaire: str
    email: str
    role: str
    description: str
    statut: str
    cree_le: str
    annulee_le: str
    annulee_par: str
    motif_annulation: str


def cellule_sure(valeur: str) -> str:
    return f"'{valeur}" if valeur.startswith(_DEBUTS_DE_FORMULE) else valeur


def _horodatage(instant: datetime | None, fuseau: ZoneInfo) -> str:
    return instant.astimezone(fuseau).strftime("%Y-%m-%d %H:%M") if instant else ""


def vers_ligne(reservation: "Reservation", fuseau: ZoneInfo) -> LigneExport:
    debut = reservation.debut.astimezone(fuseau)
    fin = reservation.fin.astimezone(fuseau)
    annulee_par = reservation.annulee_par
    return LigneExport(
        reference=str(reservation.id),
        salle=reservation.salle.code,
        batiment=reservation.salle.batiment.code,
        date=debut.strftime("%Y-%m-%d"),
        debut=debut.strftime("%H:%M"),
        fin=fin.strftime("%H:%M"),
        titulaire=reservation.titulaire.nom_complet,
        email=reservation.titulaire.email,
        role=str(reservation.titulaire.role),
        description=reservation.description,
        statut=str(reservation.statut),
        cree_le=_horodatage(reservation.cree_le, fuseau),
        annulee_le=_horodatage(reservation.annulee_le, fuseau),
        annulee_par=annulee_par.nom_complet if annulee_par else "",
        motif_annulation=reservation.motif_annulation or "",
    )


def generer_csv(lignes: Iterable[LigneExport]) -> str:
    """CSV « à la française » : séparateur point-virgule et BOM UTF-8, pour
    qu'Excel ouvre le fichier correctement d'un double-clic."""
    tampon = io.StringIO()
    tampon.write("﻿")
    ecrivain = csv.writer(tampon, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    ecrivain.writerow([ENTETES[champ.name] for champ in fields(LigneExport)])
    for ligne in lignes:
        ecrivain.writerow([cellule_sure(valeur) for valeur in astuple(ligne)])
    return tampon.getvalue()
