"""Cas d'usage d'authentification : inscription, connexion, sessions."""
import math
import uuid
from datetime import datetime, timedelta

from ..domaine.enums import Role
from ..domaine.erreurs import AuthentificationRequise, Conflit, TropDeTentatives
from ..domaine.mots_de_passe import verifier_robustesse
from .contexte import Socle
from .ports import (
    DepotSessions,
    DepotUtilisateurs,
    DepotVerrousConnexion,
    HacheurMotDePasse,
    Journal,
    SessionUtilisateur,
    Utilisateur,
    VerrouConnexion,
)

# Même message pour une adresse inconnue et un mot de passe faux : sinon on
# apprendrait, une requête à la fois, quelles adresses ont un compte.
MESSAGE_IDENTIFIANTS = "Adresse e-mail ou mot de passe incorrect."


def normaliser_email(email: str) -> str:
    return email.strip().lower()


def delai_apres_echecs(echecs: int, *, essais_libres: int, initial: timedelta,
                       maximum: timedelta) -> timedelta:
    """Attente imposée après `echecs` échecs consécutifs : rien pendant les
    premiers essais (faute de frappe), puis un délai qui double à chaque
    échec (1 s, 2 s, 4 s...) jusqu'à un plafond. Contrairement à un blocage
    long, il gêne la force brute sans permettre à n'importe qui de bloquer
    le compte d'autrui."""
    rang = echecs - essais_libres
    if rang <= 0:
        return timedelta(0)
    # Plafond appliqué sur l'exposant pour éviter de calculer 2**1000.
    return min(initial * 2 ** min(rang - 1, 30), maximum)


class ServiceAuthentification:
    def __init__(self, socle: Socle, *, utilisateurs: DepotUtilisateurs,
                 sessions: DepotSessions, verrous: DepotVerrousConnexion,
                 hacheur: HacheurMotDePasse, journal_securite: Journal) -> None:
        self._socle = socle
        self._utilisateurs = utilisateurs
        self._sessions = sessions
        self._verrous = verrous
        self._hacheur = hacheur
        self._journal_securite = journal_securite
        # Empreinte comparée quand l'adresse est inconnue : la réponse prend
        # le même temps qu'avec un vrai compte, le chronomètre ne révèle rien.
        self._empreinte_leurre = hacheur.hacher("leurre-pour-temps-constant")

    def inscrire(self, email: str, mot_de_passe: str, nom: str, prenom: str) -> Utilisateur:
        """Inscription libre, toujours en tant qu'étudiant : le rôle n'est
        jamais choisi par le client (promotion par un gestionnaire)."""
        email = normaliser_email(email)
        verifier_robustesse(mot_de_passe, email=email, nom=nom, prenom=prenom)
        deja_pris = Conflit("Un compte existe déjà avec cette adresse.", code="email_deja_utilise")
        if self._utilisateurs.par_email(email) is not None:
            raise deja_pris
        with self._socle.transaction.traduire_contraintes({"utilisateur_email_key": deja_pris}):
            utilisateur = self._utilisateurs.creer(
                email=email, nom=nom.strip(), prenom=prenom.strip(), role=Role.ETUDIANT,
                mot_de_passe=self._hacheur.hacher(mot_de_passe))
        self._socle.transaction.valider()
        self._socle.journal.evenement("utilisateur.inscrit", utilisateur=str(utilisateur.id))
        return utilisateur

    def authentifier(self, email: str, mot_de_passe: str) -> Utilisateur:
        """Vérifie les identifiants. Après quelques échecs, chaque nouvel essai
        sur la même adresse doit attendre un délai croissant (429)."""
        instant = self._socle.horloge.maintenant()
        email = normaliser_email(email)

        verrou = self._verrous.obtenir_verrouille(email)
        if verrou.bloque_jusqu_a is not None and verrou.bloque_jusqu_a > instant:
            attente = math.ceil((verrou.bloque_jusqu_a - instant).total_seconds())
            self._socle.transaction.valider()
            raise TropDeTentatives(
                f"Trop d'essais infructueux. Réessayez dans {attente} seconde(s).",
                reessayer_dans=attente)

        utilisateur = self._utilisateurs.par_email(email)
        empreinte = utilisateur.mot_de_passe if utilisateur is not None else self._empreinte_leurre
        mot_de_passe_ok = self._hacheur.verifier(empreinte, mot_de_passe)

        if utilisateur is None or not mot_de_passe_ok:
            self._enregistrer_echec(verrou, instant)
            raise AuthentificationRequise(MESSAGE_IDENTIFIANTS, code="identifiants_invalides")

        self._verrous.supprimer(email)
        self._socle.transaction.valider()
        self._journal_securite.evenement("connexion.succes", utilisateur=str(utilisateur.id))
        return utilisateur

    def _enregistrer_echec(self, verrou: VerrouConnexion, instant: datetime) -> None:
        reglages = self._socle.parametres
        # Des échecs anciens sont oubliés : seule une série rapprochée ralentit.
        if instant - verrou.dernier_echec > reglages.connexion_delai_max:
            verrou.echecs = 0
        verrou.echecs += 1
        verrou.dernier_echec = instant
        delai = delai_apres_echecs(verrou.echecs, essais_libres=reglages.connexion_essais_libres,
                                   initial=reglages.connexion_delai_initial,
                                   maximum=reglages.connexion_delai_max)
        verrou.bloque_jusqu_a = instant + delai if delai else None
        self._socle.transaction.valider()
        # L'adresse saisie n'est pas journalisée : c'est une donnée personnelle.
        self._journal_securite.evenement("connexion.echec", echecs_consecutifs=verrou.echecs,
                                         attente_s=int(delai.total_seconds()))

    def ouvrir_session(self, utilisateur: Utilisateur) -> SessionUtilisateur:
        session = self._sessions.creer(
            utilisateur_id=utilisateur.id,
            expire_le=self._socle.horloge.maintenant() + self._socle.parametres.duree_session)
        self._socle.transaction.valider()
        return session

    def session_active(self, session_id: uuid.UUID) -> bool:
        session = self._sessions.obtenir(session_id)
        return (session is not None and session.revoquee_le is None
                and session.expire_le > self._socle.horloge.maintenant())

    def revoquer_session(self, session_id: uuid.UUID) -> None:
        session = self._sessions.obtenir(session_id)
        if session is not None and session.revoquee_le is None:
            session.revoquee_le = self._socle.horloge.maintenant()
            self._socle.transaction.valider()
            self._journal_securite.evenement("session.revoquee",
                                             utilisateur=str(session.utilisateur_id))

    def utilisateur_par_id(self, identifiant: uuid.UUID) -> Utilisateur | None:
        return self._utilisateurs.obtenir(identifiant)
