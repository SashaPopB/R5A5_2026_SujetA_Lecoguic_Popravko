"""Politique de mot de passe (inscription).

La longueur minimale (12 caractères) est contrôlée par le DTO. On n'impose
aucun jeu de caractères : une phrase de plusieurs mots résiste mieux qu'un
« P@ssw0rd! ». On refuse en revanche ce qu'un attaquant essaie en premier :
les mots de passe les plus fréquents des fuites publiques, leurs variantes
(chiffres ajoutés, @ pour a...) et ceux qui reprennent le nom ou l'adresse.
"""
import re

from .erreurs import DonneesInvalides

# Racines les plus fréquentes dans les fuites publiques (listes de type
# « top 10 000 »), réduites à leurs lettres. Une liste complète pourrait être
# chargée depuis un fichier sans changer cette fonction.
_RACINES_COURANTES = frozenset({
    "motdepasse", "password", "passwort", "pass", "azerty", "azertyuiop", "qwerty",
    "qwertyuiop", "qwertz", "azertyazerty", "qwertyqwerty", "abc", "abcdef", "abcdefgh",
    "abcdefghijkl", "iloveyou", "jetaime", "soleil", "bonjour", "football", "princesse",
    "chocolat", "superman", "starwars", "welcome", "letmein", "admin", "administrateur",
    "administrator", "changeme", "etudiant", "enseignant", "gestionnaire", "universite",
    "reservation", "salle", "iut", "dragon", "monkey", "sunshine", "marseille", "doudou",
    "loulou", "nicolas", "qazwsx", "qazwsxedc", "zaqxsw", "aqwzsx",
})
_SUBSTITUTIONS = str.maketrans({"@": "a", "4": "a", "0": "o", "1": "i", "!": "i",
                                "3": "e", "$": "s", "5": "s", "7": "t"})
# Suites du clavier et des chiffres, dans les deux sens (séparées par « | »
# pour qu'une recherche ne chevauche pas deux suites).
_SUITES = "|".join(["01234567890123456789", "azertyuiopqsdfghjklmwxcvbn",
                    "qwertyuiopasdfghjklzxcvbnm", "abcdefghijklmnopqrstuvwxyz"])
_SUITES += "|" + _SUITES[::-1]
_BLOC_REPETE_MAX = 4
_LONGUEUR_MIN_INDICE = 3  # nom, prénom ou adresse trop courts pour être significatifs
_CARACTERES_DISTINCTS_MIN = 4

MESSAGE = ("Ce mot de passe est trop courant ou trop facile à deviner. "
           "Choisissez plutôt une phrase de plusieurs mots.")


def _racine(mot_de_passe: str) -> str:
    """Le mot sans ses chiffres et symboles de début et de fin, après
    annulation des substitutions classiques : P@ssword1234 -> password."""
    noyau = re.sub(r"^[\d\W_]+|[\d\W_]+$", "", mot_de_passe.lower())
    return re.sub(r"[^a-z]", "", noyau.translate(_SUBSTITUTIONS))


def _motif_repete(texte: str) -> bool:
    """Vrai pour « azerazerazer » ou « 199019901990 » : un petit bloc répété."""
    return any(texte == (texte[:taille] * (len(texte) // taille + 1))[:len(texte)]
               for taille in range(1, _BLOC_REPETE_MAX + 1))


def _indices_personnels(email: str, nom: str, prenom: str) -> set[str]:
    partie_locale = email.split("@", 1)[0]
    morceaux = re.split(r"[._+-]", partie_locale) + [partie_locale, nom, prenom]
    return {m.strip().lower() for m in morceaux if len(m.strip()) >= _LONGUEUR_MIN_INDICE}


def est_previsible(mot_de_passe: str, *, email: str = "", nom: str = "",
                   prenom: str = "") -> bool:
    minuscule = mot_de_passe.lower()
    if len(set(minuscule)) < _CARACTERES_DISTINCTS_MIN:  # 111111111111, abababababab
        return True
    if minuscule in _SUITES or _motif_repete(minuscule):  # 123456789012, azerazerazer
        return True
    if _racine(mot_de_passe) in _RACINES_COURANTES:  # Motdepasse2026!, P@ssword1234
        return True
    return any(indice in minuscule for indice in _indices_personnels(email, nom, prenom))


def verifier_robustesse(mot_de_passe: str, *, email: str, nom: str, prenom: str) -> None:
    if est_previsible(mot_de_passe, email=email, nom=nom, prenom=prenom):
        raise DonneesInvalides(MESSAGE, code="mot_de_passe_previsible")
