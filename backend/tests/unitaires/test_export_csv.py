"""Export CSV (A-10) : format et protection contre l'injection de formules."""
import csv
import io

import pytest

from app.services.export import LigneExport, cellule_sure, generer_csv


def ligne(**valeurs: str) -> LigneExport:
    base = {nom: "" for nom in LigneExport.__dataclass_fields__}
    base.update(reference="r1", salle="D101", description="Réunion", statut="active")
    base.update(valeurs)
    return LigneExport(**base)


@pytest.mark.parametrize("valeur", ["=HYPERLINK(\"http://x\")", "+1", "-2+3", "@SUM(A1)"])
def test_formules_neutralisees(valeur):
    assert cellule_sure(valeur) == "'" + valeur


def test_texte_ordinaire_inchange():
    assert cellule_sure("Révisions BDD") == "Révisions BDD"


def test_csv_lisible_par_excel_et_par_csv():
    contenu = generer_csv([ligne(description="Projet ; « SAE »\n- démo", titulaire="=1+1")])
    assert contenu.startswith("﻿")  # BOM : accents corrects dans Excel
    lignes = list(csv.reader(io.StringIO(contenu.lstrip("﻿")), delimiter=";"))
    assert lignes[0][0] == "Référence"
    assert lignes[1][lignes[0].index("Description")] == "Projet ; « SAE »\n- démo"
    assert lignes[1][lignes[0].index("Réservé par")] == "'=1+1"
