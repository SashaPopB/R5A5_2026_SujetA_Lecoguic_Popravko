"""Fermeture et réouverture de créneaux par le gestionnaire (A-07)."""
import uuid
from dataclasses import dataclass
from datetime import datetime

from ..domaine.creneaux import construire_plage, verifier_non_passe
from ..domaine.enums import EtatSalle
from ..domaine.erreurs import Conflit, RessourceIntrouvable
from .contexte import PublicationPlanning, Socle, exiger_gestionnaire
from .ports import DepotFermetures, DepotReservations, DepotSalles, Fermeture, Utilisateur
from .reservations import annuler_toutes

LONGUEUR_MAX_MOTIF_ANNULATION = 200


@dataclass(frozen=True)
class DemandeFermeture:
    salle_id: uuid.UUID
    debut: datetime
    fin: datetime
    motif: str


class ServiceFermetures:
    def __init__(self, socle: Socle, *, fermetures: DepotFermetures, salles: DepotSalles,
                 reservations: DepotReservations, publication: PublicationPlanning) -> None:
        self._socle = socle
        self._fermetures = fermetures
        self._salles = salles
        self._reservations = reservations
        self._publication = publication

    def fermer(self, acteur: Utilisateur, demande: DemandeFermeture) -> tuple[Fermeture, int]:
        """Ferme une plage horaire d'une salle, éventuellement sur plusieurs
        jours. Les réservations actives de la plage sont annulées avec le
        motif de fermeture, que leurs titulaires voient dans « Mes
        réservations ». Retourne la fermeture et le nombre d'annulations."""
        exiger_gestionnaire(acteur.role)
        instant = self._socle.horloge.maintenant()
        plage = construire_plage(demande.debut, demande.fin, self._socle.parametres.fuseau)
        verifier_non_passe(plage, instant)

        salle = self._salles.obtenir_pour_modification(demande.salle_id)
        if salle is None or salle.etat == EtatSalle.RETIREE:
            raise RessourceIntrouvable("Salle inconnue.", code="salle_introuvable")
        existante = Conflit("Une fermeture existe déjà sur une partie de cette plage.",
                            code="fermeture_existante")
        if self._fermetures.chevauchant(plage.debut, plage.fin, salle_id=salle.id):
            raise existante

        motif = demande.motif.strip()
        with self._socle.transaction.traduire_contraintes(
                {"fermeture_sans_chevauchement": existante}):
            fermeture = self._fermetures.creer(salle_id=salle.id, debut=plage.debut,
                                               fin=plage.fin, motif=motif, cree_par_id=acteur.id)
        a_annuler = self._reservations.actives_chevauchant(plage.debut, plage.fin,
                                                           salle_id=salle.id)
        annuler_toutes(a_annuler, par=acteur.id, instant=instant,
                       motif=f"Créneau fermé : {motif}"[:LONGUEUR_MAX_MOTIF_ANNULATION])
        self._socle.transaction.valider()

        self._socle.journal.evenement(
            "fermeture.creee", fermeture=str(fermeture.id), salle=str(salle.id),
            utilisateur=str(acteur.id), debut=plage.debut.isoformat(),
            fin=plage.fin.isoformat(), reservations_annulees=len(a_annuler))
        self._publication.creneau_modifie(salle.id, plage.debut, plage.fin)
        return fermeture, len(a_annuler)

    def rouvrir(self, acteur: Utilisateur, fermeture_id: uuid.UUID) -> None:
        exiger_gestionnaire(acteur.role)
        fermeture = self._fermetures.obtenir(fermeture_id)
        if fermeture is None:
            raise RessourceIntrouvable("Fermeture introuvable.", code="fermeture_introuvable")
        salle_id, debut, fin = fermeture.salle_id, fermeture.debut, fermeture.fin
        self._fermetures.supprimer(fermeture)
        self._socle.transaction.valider()
        self._socle.journal.evenement("fermeture.supprimee", fermeture=str(fermeture_id),
                                      salle=str(salle_id), utilisateur=str(acteur.id))
        self._publication.creneau_modifie(salle_id, debut, fin)
