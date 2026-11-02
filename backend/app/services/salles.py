"""Administration des salles (A-07) et référentiel des bâtiments."""
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

from ..domaine.creneaux import Intervalle, verifier_horaires_coherents, verifier_horaires_salle
from ..domaine.enums import EtatSalle
from ..domaine.erreurs import Conflit, DonneesInvalides, RessourceIntrouvable
from .contexte import PublicationPlanning, Socle, exiger_gestionnaire
from .ports import Batiment, DepotBatiments, DepotReservations, DepotSalles, Salle, Utilisateur
from .reservations import annuler_toutes

MOTIFS_ANNULATION = {
    EtatSalle.FERMEE: "Salle fermée par le gestionnaire",
    EtatSalle.RETIREE: "Salle retirée du planning",
}
MOTIF_HORAIRES = "Horaires d'ouverture de la salle modifiés"

# Champs modifiables d'une salle. Le code reste stable : il est imprimé sur
# les portes et figure dans l'historique.
CHAMPS_MODIFIABLES = ("nom", "batiment_id", "etage", "capacite",
                      "heure_ouverture", "heure_fermeture", "etat")


@dataclass(frozen=True)
class DonneesSalle:
    code: str
    batiment_id: uuid.UUID
    capacite: int
    nom: str | None = None
    etage: int = 0
    heure_ouverture: time = time(8)
    heure_fermeture: time = time(20)


@dataclass(frozen=True)
class ModificationSalle:
    """Seuls les champs présents dans `valeurs` sont modifiés (PATCH)."""

    valeurs: dict[str, Any] = field(default_factory=dict)


class ServiceSalles:
    def __init__(self, socle: Socle, *, salles: DepotSalles, batiments: DepotBatiments,
                 reservations: DepotReservations, publication: PublicationPlanning) -> None:
        self._socle = socle
        self._salles = salles
        self._batiments = batiments
        self._reservations = reservations
        self._publication = publication

    def lister_batiments(self) -> Sequence[Batiment]:
        return self._batiments.lister()

    def lister_proposees(self) -> Sequence[Salle]:
        """Salles visibles dans le planning (les salles retirées n'y sont plus)."""
        return self._salles.lister_proposees()

    def lister_toutes(self, acteur: Utilisateur) -> Sequence[Salle]:
        exiger_gestionnaire(acteur.role)
        return self._salles.lister_toutes()

    def compter_reservations_a_venir(self, salles: Sequence[Salle]) -> dict[uuid.UUID, int]:
        return self._salles.compter_reservations_a_venir([s.id for s in salles],
                                                         self._socle.horloge.maintenant())

    def creer(self, acteur: Utilisateur, donnees: DonneesSalle) -> Salle:
        exiger_gestionnaire(acteur.role)
        verifier_horaires_coherents(donnees.heure_ouverture, donnees.heure_fermeture)
        if self._batiments.obtenir(donnees.batiment_id) is None:
            raise DonneesInvalides("Bâtiment inconnu.", code="batiment_introuvable")
        code_pris = Conflit(f"Le code {donnees.code} est déjà utilisé.", code="code_salle_existant")
        if self._salles.code_existe(donnees.code):
            raise code_pris

        with self._socle.transaction.traduire_contraintes({"salle_code_unique": code_pris}):
            salle = self._salles.creer(
                code=donnees.code, nom=donnees.nom or None, batiment_id=donnees.batiment_id,
                etage=donnees.etage, capacite=donnees.capacite,
                heure_ouverture=donnees.heure_ouverture,
                heure_fermeture=donnees.heure_fermeture)
        self._socle.transaction.valider()
        self._socle.journal.evenement("salle.creee", salle=str(salle.id),
                                      utilisateur=str(acteur.id))
        self._publication.salles_modifiees()
        return salle

    def modifier(self, acteur: Utilisateur, salle_id: uuid.UUID,
                 modification: ModificationSalle) -> tuple[Salle, int]:
        """Modifie une salle. Retourne la salle et le nombre de réservations
        annulées parce qu'elles devenaient impossibles (salle fermée ou
        retirée, horaires réduits)."""
        exiger_gestionnaire(acteur.role)
        valeurs = {cle: valeur for cle, valeur in modification.valeurs.items()
                   if cle in CHAMPS_MODIFIABLES}
        salle = self._salles.obtenir_pour_modification(salle_id)
        if salle is None:
            raise RessourceIntrouvable("Salle inconnue.", code="salle_introuvable")
        if "batiment_id" in valeurs and self._batiments.obtenir(valeurs["batiment_id"]) is None:
            raise DonneesInvalides("Bâtiment inconnu.", code="batiment_introuvable")
        verifier_horaires_coherents(valeurs.get("heure_ouverture", salle.heure_ouverture),
                                    valeurs.get("heure_fermeture", salle.heure_fermeture))

        ancien_etat = salle.etat
        # Affectation champ par champ, limitée à la liste blanche ci-dessus :
        # jamais de fusion en bloc du corps reçu dans l'entité.
        for cle, valeur in valeurs.items():
            setattr(salle, cle, valeur)
        annulees = self._annuler_reservations_devenues_impossibles(acteur, salle)
        self._socle.transaction.valider()

        self._socle.journal.evenement(
            "salle.modifiee", salle=str(salle.id), utilisateur=str(acteur.id),
            champs=sorted(valeurs), ancien_etat=str(ancien_etat), etat=str(salle.etat),
            reservations_annulees=annulees)
        self._publication.salles_modifiees()
        return salle, annulees

    def _annuler_reservations_devenues_impossibles(self, acteur: Utilisateur,
                                                   salle: Salle) -> int:
        instant = self._socle.horloge.maintenant()
        a_venir = self._reservations.actives_a_venir_salle(salle.id, instant)
        if salle.etat in MOTIFS_ANNULATION:
            cibles, motif = a_venir, MOTIFS_ANNULATION[salle.etat]
        else:
            cibles = [r for r in a_venir if not self._respecte_horaires(r.debut, r.fin, salle)]
            motif = MOTIF_HORAIRES
        annuler_toutes(cibles, par=acteur.id, instant=instant, motif=motif)
        return len(cibles)

    def _respecte_horaires(self, debut: datetime, fin: datetime, salle: Salle) -> bool:
        fuseau = self._socle.parametres.fuseau
        try:
            verifier_horaires_salle(Intervalle(debut.astimezone(fuseau), fin.astimezone(fuseau)),
                                    salle.heure_ouverture, salle.heure_fermeture)
        except DonneesInvalides:
            return False
        return True
