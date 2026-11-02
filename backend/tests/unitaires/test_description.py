"""Description mise en forme (A-02) : validation côté serveur."""
import pytest

from app.domaine.description import normaliser_description, url_autorisee
from app.domaine.erreurs import DonneesInvalides

LONGUEUR_MAX = 2000


def test_markdown_autorise_conserve_tel_quel():
    texte = "**Projet** *SAE*\n- maquettes\n1. démo\n[sujet](https://moodle.example.org/42)"
    assert normaliser_description(texte, LONGUEUR_MAX) == texte


def test_espaces_et_fins_de_ligne_normalises():
    assert normaliser_description("  ligne 1\r\nligne 2  ", LONGUEUR_MAX) == "ligne 1\nligne 2"


@pytest.mark.parametrize("texte", ["", "   ", "\n\n"])
def test_description_vide_refusee(texte):
    with pytest.raises(DonneesInvalides):
        normaliser_description(texte, LONGUEUR_MAX)


def test_description_trop_longue_refusee():
    with pytest.raises(DonneesInvalides):
        normaliser_description("a" * (LONGUEUR_MAX + 1), LONGUEUR_MAX)


@pytest.mark.parametrize("lien", [
    "javascript:alert(1)",
    "JavaScript:alert(document.cookie)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "vbscript:msgbox(1)",
    "//exemple.org/sans-schema",
    "https:///sans-hote",
])
def test_liens_dangereux_refuses(lien):
    with pytest.raises(DonneesInvalides) as erreur:
        normaliser_description(f"voir [ici]({lien})", LONGUEUR_MAX)
    assert erreur.value.code == "lien_non_autorise"


def test_caracteres_de_controle_refuses():
    with pytest.raises(DonneesInvalides):
        normaliser_description("texte\x00caché", LONGUEUR_MAX)


def test_html_brut_stocke_comme_du_texte():
    # Le HTML n'est jamais interprété (rendu en éléments React) : il est
    # simplement conservé comme texte.
    assert normaliser_description("<b>gras</b>", LONGUEUR_MAX) == "<b>gras</b>"


@pytest.mark.parametrize("url,attendu", [
    ("https://exemple.org", True),
    ("http://exemple.org/doc?id=1", True),
    ("mailto:prof@iut.fr", True),
    ("ftp://exemple.org", False),
    ("mailto:", False),
])
def test_url_autorisee(url, attendu):
    assert url_autorisee(url) is attendu
