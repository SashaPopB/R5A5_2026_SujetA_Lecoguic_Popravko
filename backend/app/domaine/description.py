"""Description mise en forme d'une réservation (A-02).

Format : Markdown restreint (**gras**, *italique*, listes « - » et « 1. »,
liens [texte](url)). Le serveur stocke du texte, jamais du HTML : le
frontend construit lui-même les éléments affichés, donc rien de ce que
l'utilisateur tape n'est interprété comme du code par le navigateur.

Le serveur vérifie quand même les liens : un lien « javascript: » n'a rien
à faire dans la base, même si l'affichage le neutraliserait.
"""
import re
import unicodedata
from urllib.parse import urlsplit

from .erreurs import DonneesInvalides

SCHEMAS_AUTORISES = frozenset({"http", "https", "mailto"})

# [texte](url) : le texte ne contient ni « ] » ni retour à la ligne ; l'URL
# s'arrête à la première parenthèse fermante ou au premier blanc.
_LIEN_MARKDOWN = re.compile(r"\[([^\]\n]*)\]\(([^)\s]*)\)")


def url_autorisee(url: str) -> bool:
    morceaux = urlsplit(url.strip())
    schema = morceaux.scheme.lower()
    if schema not in SCHEMAS_AUTORISES:
        return False
    # http(s) exige un hôte ; mailto exige une adresse.
    return bool(morceaux.netloc) if schema != "mailto" else bool(morceaux.path)


def normaliser_description(texte: str, longueur_max: int) -> str:
    """Nettoie et valide une description ; renvoie le texte à stocker."""
    texte = texte.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not texte:
        raise DonneesInvalides("La description est obligatoire.", code="description_vide")
    if len(texte) > longueur_max:
        raise DonneesInvalides(
            f"La description dépasse {longueur_max} caractères.",
            code="description_trop_longue",
        )
    # Caractères de contrôle (hors saut de ligne et tabulation) : invisibles,
    # ils ne servent qu'à tromper l'affichage ou les exports.
    if any(unicodedata.category(c) == "Cc" and c not in "\n\t" for c in texte):
        raise DonneesInvalides("La description contient des caractères non autorisés.",
                               code="description_caracteres_interdits")
    for lien in _LIEN_MARKDOWN.finditer(texte):
        if not url_autorisee(lien.group(2)):
            raise DonneesInvalides(
                "Seuls les liens http://, https:// et mailto: sont acceptés.",
                code="lien_non_autorise",
                details={"lien": lien.group(2)[:200]},
            )
    return texte
