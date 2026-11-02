"""Validation des entrées par les DTO."""
import uuid

import pytest
from pydantic import ValidationError

from app.api import dto


def test_inscription_refuse_un_role_envoye_par_le_client():
    with pytest.raises(ValidationError) as erreur:
        dto.InscriptionEntree.model_validate({
            "email": "etud@iut.fr", "mot_de_passe": "x" * 12, "nom": "IUT", "prenom": "Étudiant",
            "role": "gestionnaire",
        })
    assert erreur.value.errors()[0]["type"] == "extra_forbidden"


def test_email_normalise_en_minuscules():
    entree = dto.ConnexionEntree.model_validate({"email": "  Prof@IUT.FR ", "mot_de_passe": "x"})
    assert entree.email == "prof@iut.fr"


def test_mot_de_passe_trop_court_a_l_inscription():
    with pytest.raises(ValidationError):
        dto.InscriptionEntree.model_validate(
            {"email": "etud@iut.fr", "mot_de_passe": "court", "nom": "IUT", "prenom": "Étudiant"})


def test_mot_de_passe_jamais_tronque_ni_nettoye():
    entree = dto.ConnexionEntree.model_validate({"email": "etud@iut.fr", "mot_de_passe": " a b "})
    assert entree.mot_de_passe == " a b "


def test_code_salle_mis_en_majuscules():
    entree = dto.SalleCreationEntree.model_validate(
        {"code": "d101", "batiment_id": str(uuid.uuid4()), "capacite": 10})
    assert entree.code == "D101"


def test_modification_partielle_refuse_null_sauf_pour_le_nom():
    assert dto.SalleModificationEntree.model_validate({"nom": None}).model_fields_set == {"nom"}
    with pytest.raises(ValidationError):
        dto.SalleModificationEntree.model_validate({"capacite": None})


def test_annulation_n_accepte_que_le_statut_annulee():
    dto.AnnulationEntree.model_validate({"statut": "annulee"})
    with pytest.raises(ValidationError):
        dto.AnnulationEntree.model_validate({"statut": "active"})


def test_heures_serialisees_en_hh_mm():
    salle = dto.SalleSortie(
        id=uuid.uuid4(), code="D101", nom=None,
        batiment=dto.BatimentSortie(id=uuid.uuid4(), code="A", nom="Bâtiment A"),
        etage=1, capacite=8, heure_ouverture="08:00", heure_fermeture="20:00", etat="ouverte",
    )
    donnees = salle.model_dump(mode="json")
    assert (donnees["heure_ouverture"], donnees["heure_fermeture"]) == ("08:00", "20:00")
