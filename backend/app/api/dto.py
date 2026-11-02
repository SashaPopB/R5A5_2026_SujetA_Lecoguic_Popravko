"""DTO : forme des données échangées avec le frontend.

Ils sont distincts des modèles de persistance : si la base change, seuls les
mappers (api/mappers.py) bougent, pas le contrat de l'API. Les mêmes classes
servent à la validation des entrées et à la documentation OpenAPI.
"""
import datetime as dt
import uuid
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    model_validator,
)

from ..domaine.enums import EtatSalle, Role, StatutReservation

# Adresse e-mail volontairement simple : « quelque chose@domaine.extension »,
# sans espace ni second @. La vraie preuve qu'une adresse existe, ce serait
# un e-mail de confirmation (hors périmètre : pas de notification par mail).
Email = Annotated[str, StringConstraints(
    strip_whitespace=True, to_lower=True, min_length=3, max_length=254,
    pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
)]
MotDePasse = Annotated[str, StringConstraints(min_length=12, max_length=128)]
MotDePasseSaisi = Annotated[str, StringConstraints(min_length=1, max_length=128)]
TexteCourt = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Motif = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# Code de salle tel qu'affiché sur la porte : lettres, chiffres, tirets
# (20 caractères au plus), enregistré en majuscules. Pydantic vérifie le
# motif avant la mise en majuscules, d'où les minuscules acceptées ici.
CodeSalle = Annotated[str, StringConstraints(
    strip_whitespace=True, to_upper=True, pattern=r"^[A-Za-z0-9][A-Za-z0-9-]{0,19}$",
)]
HeureHM = Annotated[dt.time, PlainSerializer(lambda h: h.strftime("%H:%M"), return_type=str)]


class Entree(BaseModel):
    """Toute entrée refuse les champs inconnus : envoyer « role » à
    l'inscription est une erreur, pas une option ignorée."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------- entrées
class InscriptionEntree(Entree):
    email: Email
    mot_de_passe: MotDePasse
    nom: TexteCourt
    prenom: TexteCourt


class ConnexionEntree(Entree):
    email: Email
    mot_de_passe: MotDePasseSaisi


class ReservationEntree(Entree):
    salle_id: uuid.UUID
    debut: dt.datetime = Field(description="Heure pleine. Sans fuseau : heure de Paris.")
    fin: dt.datetime = Field(description="Heure pleine, le même jour que le début.")
    description: str = Field(min_length=1, max_length=2000,
                             description="Markdown restreint : **gras**, *italique*, "
                                         "listes « - » / « 1. », liens [texte](https://...).")


class AnnulationEntree(Entree):
    statut: Literal[StatutReservation.ANNULEE]
    motif: Motif | None = None


class SalleCreationEntree(Entree):
    code: CodeSalle
    nom: TexteCourt | None = None
    batiment_id: uuid.UUID
    etage: int = Field(0, ge=-5, le=50)
    capacite: int = Field(ge=1, le=500)
    heure_ouverture: dt.time = dt.time(8)
    heure_fermeture: dt.time = dt.time(20)


class SalleModificationEntree(Entree):
    """PATCH partiel : seuls les champs envoyés sont modifiés. Seul « nom »
    peut être remis à null (salle sans nom d'usage)."""

    nom: TexteCourt | None = None
    batiment_id: uuid.UUID | None = None
    etage: int | None = Field(None, ge=-5, le=50)
    capacite: int | None = Field(None, ge=1, le=500)
    heure_ouverture: dt.time | None = None
    heure_fermeture: dt.time | None = None
    etat: EtatSalle | None = None

    @model_validator(mode="after")
    def refuser_null(self) -> "SalleModificationEntree":
        nuls = sorted(champ for champ in self.model_fields_set - {"nom"}
                      if getattr(self, champ) is None)
        if nuls:
            raise ValueError(f"Ces champs ne peuvent pas valoir null : {', '.join(nuls)}")
        return self


class FermetureEntree(Entree):
    salle_id: uuid.UUID
    debut: dt.datetime
    fin: dt.datetime
    motif: Motif


class RoleEntree(Entree):
    role: Role


# ------------------------------------------------- paramètres de requête
class PlanningParametres(Entree):
    date: dt.date | None = Field(None, description="Jour affiché (défaut : aujourd'hui).")


class SallesParametres(Entree):
    inclure_retirees: bool = False


class EvenementsParametres(Entree):
    depuis: Annotated[str, StringConstraints(max_length=64)] | None = Field(
        None, description="Dernier identifiant reçu, si le client rouvre lui-même le flux.")


class MesReservationsParametres(Entree):
    periode: Literal["a_venir", "passees"] = "a_venir"
    page: int = Field(1, ge=1)
    taille: int = Field(20, ge=1, le=100)


class HistoriqueParametres(Entree):
    salle_id: uuid.UUID | None = None
    du: dt.date | None = None
    au: dt.date | None = None
    statut: StatutReservation | None = None
    recherche: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    page: int = Field(1, ge=1)
    taille: int = Field(50, ge=1, le=200)


class ExportParametres(Entree):
    du: dt.date
    au: dt.date


class UtilisateursParametres(Entree):
    recherche: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    page: int = Field(1, ge=1)
    taille: int = Field(50, ge=1, le=200)


# ---------------------------------------------------------------- sorties
class UtilisateurSortie(BaseModel):
    id: uuid.UUID
    email: str
    nom: str
    prenom: str
    role: Role


class PersonneSortie(BaseModel):
    id: uuid.UUID
    nom: str
    prenom: str
    email: str
    role: Role


class BatimentSortie(BaseModel):
    id: uuid.UUID
    code: str
    nom: str


class SalleSortie(BaseModel):
    id: uuid.UUID
    code: str
    nom: str | None
    batiment: BatimentSortie
    etage: int
    capacite: int
    heure_ouverture: HeureHM
    heure_fermeture: HeureHM
    etat: EtatSalle
    reservations_a_venir: int | None = Field(
        None, description="Renseigné pour le gestionnaire uniquement.")


class SalleModifieeSortie(SalleSortie):
    reservations_annulees: int


class SalleResume(BaseModel):
    id: uuid.UUID
    code: str
    nom: str | None


class ReservationPlanningSortie(BaseModel):
    id: uuid.UUID
    salle_id: uuid.UUID
    debut: dt.datetime
    fin: dt.datetime
    est_a_moi: bool
    titulaire: PersonneSortie | None = Field(
        description="Visible du titulaire et du gestionnaire seulement.")
    description: str | None = Field(
        description="Visible du titulaire et du gestionnaire seulement.")


class FermetureSortie(BaseModel):
    id: uuid.UUID
    salle_id: uuid.UUID
    debut: dt.datetime
    fin: dt.datetime
    motif: str


class FermetureCreeeSortie(FermetureSortie):
    reservations_annulees: int


class PlanningSortie(BaseModel):
    date: dt.date
    jour_ouvert: bool
    salles: list[SalleSortie]
    reservations: list[ReservationPlanningSortie]
    fermetures: list[FermetureSortie]


class ReservationSortie(BaseModel):
    id: uuid.UUID
    salle: SalleResume
    debut: dt.datetime
    fin: dt.datetime
    description: str
    statut: StatutReservation
    titulaire: PersonneSortie
    cree_le: dt.datetime
    annulee_le: dt.datetime | None
    annulee_par: PersonneSortie | None
    motif_annulation: str | None


class PageReservationsSortie(BaseModel):
    elements: list[ReservationSortie]
    total: int
    page: int
    taille: int


class PageUtilisateursSortie(BaseModel):
    elements: list[UtilisateurSortie]
    total: int
    page: int
    taille: int


class ErreurSortie(BaseModel):
    code: str = Field(description="Code stable, exploitable par le client.")
    message: str = Field(description="Message lisible, en français.")
    details: Any | None = None


class SanteSortie(BaseModel):
    statut: Literal["ok", "degrade"]
    base_de_donnees: Literal["ok", "indisponible"]
