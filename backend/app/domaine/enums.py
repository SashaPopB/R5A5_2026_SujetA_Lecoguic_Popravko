"""Vocabulaire du domaine, partagé par toutes les couches."""
from enum import StrEnum


class Role(StrEnum):
    ETUDIANT = "etudiant"
    ENSEIGNANT = "enseignant"
    GESTIONNAIRE = "gestionnaire"


class EtatSalle(StrEnum):
    OUVERTE = "ouverte"   # réservable
    FERMEE = "fermee"     # visible au planning mais non réservable
    RETIREE = "retiree"   # retirée du planning, conservée pour l'historique


class StatutReservation(StrEnum):
    ACTIVE = "active"
    ANNULEE = "annulee"


# Le sujet décrit l'étudiant et l'enseignant comme ceux qui réservent ; le
# gestionnaire administre (il ferme des créneaux au lieu de les réserver).
ROLES_QUI_RESERVENT = frozenset({Role.ETUDIANT, Role.ENSEIGNANT})
