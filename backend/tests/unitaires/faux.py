"""Implémentations en mémoire des contrats de app/services/ports.py.

Elles permettent de tester les cas d'usage sans base de données ni Flask :
c'est le bénéfice direct de l'injection de dépendances. Les contraintes de la
base (EXCLUDE, unicité) ne sont pas reproduites : les services font leurs
vérifications avant d'écrire, la base n'est que le dernier rempart.
"""
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domaine.enums import EtatSalle, Role, StatutReservation
from app.services.auth import ServiceAuthentification
from app.services.contexte import ParametresMetier, PublicationPlanning, Socle
from app.services.fermetures import ServiceFermetures
from app.services.planning import ServicePlanning
from app.services.ports import FiltresReservations
from app.services.reservations import ServiceReservations
from app.services.salles import ServiceSalles
from app.services.utilisateurs import ServiceUtilisateurs

PARIS = ZoneInfo("Europe/Paris")
LUNDI = datetime(2026, 11, 2, tzinfo=PARIS)  # un lundi, jour ouvert


def a(heure: int, jour: datetime = LUNDI) -> datetime:
    return jour.replace(hour=heure)


# ------------------------------------------------------------- entités


@dataclass
class Utilisateur:
    email: str
    nom: str
    prenom: str
    role: Role
    mot_de_passe: str
    id: uuid.UUID = field(default_factory=uuid.uuid4)

    @property
    def nom_complet(self) -> str:
        return f"{self.prenom} {self.nom}"


@dataclass
class Session:
    utilisateur_id: uuid.UUID
    expire_le: datetime
    revoquee_le: datetime | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Verrou:
    email: str
    echecs: int = 0
    dernier_echec: datetime = LUNDI
    bloque_jusqu_a: datetime | None = None


@dataclass
class Batiment:
    code: str
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Salle:
    code: str
    batiment_id: uuid.UUID
    capacite: int = 30
    nom: str | None = None
    etage: int = 0
    heure_ouverture: time = time(8)
    heure_fermeture: time = time(20)
    etat: EtatSalle = EtatSalle.OUVERTE
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Reservation:
    salle_id: uuid.UUID
    utilisateur_id: uuid.UUID
    debut: datetime
    fin: datetime
    description: str = ""
    statut: StatutReservation = StatutReservation.ACTIVE
    annulee_le: datetime | None = None
    annulee_par_id: uuid.UUID | None = None
    motif_annulation: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Fermeture:
    salle_id: uuid.UUID
    debut: datetime
    fin: datetime
    motif: str
    cree_par_id: uuid.UUID
    id: uuid.UUID = field(default_factory=uuid.uuid4)


def _chevauche(debut: datetime, fin: datetime, autre_debut: datetime, autre_fin: datetime) -> bool:
    return debut < autre_fin and autre_debut < fin  # intervalles [début, fin)


def _page(elements: list, page: int, taille: int) -> tuple[list, int]:
    return elements[(page - 1) * taille:page * taille], len(elements)


# --------------------------------------------------------------- dépôts


@dataclass
class Memoire:
    utilisateurs: list[Utilisateur] = field(default_factory=list)
    sessions: list[Session] = field(default_factory=list)
    verrous: dict[str, Verrou] = field(default_factory=dict)
    batiments: list[Batiment] = field(default_factory=list)
    salles: list[Salle] = field(default_factory=list)
    reservations: list[Reservation] = field(default_factory=list)
    fermetures: list[Fermeture] = field(default_factory=list)


class DepotUtilisateurs:
    def __init__(self, memoire: Memoire) -> None:
        self.m = memoire

    def obtenir(self, identifiant):
        return next((u for u in self.m.utilisateurs if u.id == identifiant), None)

    def par_email(self, email):
        return next((u for u in self.m.utilisateurs if u.email == email), None)

    def creer(self, **champs):
        utilisateur = Utilisateur(**champs)
        self.m.utilisateurs.append(utilisateur)
        return utilisateur

    def verrouiller(self, identifiant):
        pass

    def rechercher(self, recherche, page, taille):
        trouves = [u for u in self.m.utilisateurs
                   if not recherche or recherche.lower() in f"{u.email} {u.nom} {u.prenom}".lower()]
        return _page(sorted(trouves, key=lambda u: (u.nom, u.prenom)), page, taille)


class DepotSessions:
    def __init__(self, memoire: Memoire) -> None:
        self.m = memoire

    def creer(self, **champs):
        session = Session(**champs)
        self.m.sessions.append(session)
        return session

    def obtenir(self, identifiant):
        return next((s for s in self.m.sessions if s.id == identifiant), None)


class DepotVerrous:
    def __init__(self, memoire: Memoire) -> None:
        self.m = memoire

    def obtenir_verrouille(self, email):
        return self.m.verrous.setdefault(email, Verrou(email))

    def supprimer(self, email):
        self.m.verrous.pop(email, None)


class DepotBatiments:
    def __init__(self, memoire: Memoire) -> None:
        self.m = memoire

    def lister(self):
        return list(self.m.batiments)

    def obtenir(self, identifiant):
        return next((b for b in self.m.batiments if b.id == identifiant), None)


class DepotSalles:
    def __init__(self, memoire: Memoire) -> None:
        self.m = memoire

    def lister_toutes(self):
        return list(self.m.salles)

    def lister_proposees(self):
        return [s for s in self.m.salles if s.etat != EtatSalle.RETIREE]

    def obtenir_pour_modification(self, identifiant):
        return next((s for s in self.m.salles if s.id == identifiant), None)

    def code_existe(self, code):
        return any(s.code.upper() == code.upper() for s in self.m.salles)

    def creer(self, **champs):
        salle = Salle(**champs)
        self.m.salles.append(salle)
        return salle

    def compter_reservations_a_venir(self, salle_ids, instant):
        return {sid: sum(1 for r in self.m.reservations if r.salle_id == sid
                         and r.statut == StatutReservation.ACTIVE and r.fin > instant)
                for sid in salle_ids}


class DepotReservations:
    def __init__(self, memoire: Memoire) -> None:
        self.m = memoire

    def creer(self, **champs):
        reservation = Reservation(**champs)
        self.m.reservations.append(reservation)
        return reservation

    def obtenir_pour_modification(self, identifiant):
        return next((r for r in self.m.reservations if r.id == identifiant), None)

    def actives_chevauchant(self, debut, fin, *, salle_id=None, utilisateur_id=None):
        return sorted((r for r in self.m.reservations
                       if r.statut == StatutReservation.ACTIVE
                       and _chevauche(debut, fin, r.debut, r.fin)
                       and salle_id in (None, r.salle_id)
                       and utilisateur_id in (None, r.utilisateur_id)), key=lambda r: r.debut)

    def actives_a_venir_salle(self, salle_id, instant):
        return [r for r in self.m.reservations if r.salle_id == salle_id
                and r.statut == StatutReservation.ACTIVE and r.fin > instant]

    def a_venir_du_titulaire(self, utilisateur_id, instant, page, taille):
        trouvees = [r for r in self.m.reservations if r.utilisateur_id == utilisateur_id
                    and r.statut == StatutReservation.ACTIVE and r.fin > instant]
        return _page(sorted(trouvees, key=lambda r: r.debut), page, taille)

    def passees_du_titulaire(self, utilisateur_id, instant, page, taille):
        trouvees = [r for r in self.m.reservations if r.utilisateur_id == utilisateur_id
                    and (r.statut == StatutReservation.ANNULEE or r.fin <= instant)]
        return _page(sorted(trouvees, key=lambda r: r.debut, reverse=True), page, taille)

    def rechercher(self, filtres: FiltresReservations, page, taille):
        trouvees = [r for r in self.m.reservations
                    if filtres.salle_id in (None, r.salle_id)
                    and (filtres.debut_min is None or r.debut >= filtres.debut_min)
                    and (filtres.debut_max is None or r.debut < filtres.debut_max)
                    and filtres.statut in (None, r.statut)]
        return _page(sorted(trouvees, key=lambda r: r.debut, reverse=True), page, taille)

    def sur_periode(self, debut, fin):
        return sorted((r for r in self.m.reservations if debut <= r.debut < fin),
                      key=lambda r: r.debut)


class DepotFermetures:
    def __init__(self, memoire: Memoire) -> None:
        self.m = memoire

    def creer(self, **champs):
        fermeture = Fermeture(**champs)
        self.m.fermetures.append(fermeture)
        return fermeture

    def obtenir(self, identifiant):
        return next((f for f in self.m.fermetures if f.id == identifiant), None)

    def supprimer(self, fermeture):
        self.m.fermetures.remove(fermeture)

    def chevauchant(self, debut, fin, *, salle_id=None):
        return [f for f in self.m.fermetures if _chevauche(debut, fin, f.debut, f.fin)
                and salle_id in (None, f.salle_id)]


# --------------------------------------------------- outils transverses


class FausseTransaction:
    def __init__(self) -> None:
        self.validations = 0

    def valider(self) -> None:
        self.validations += 1

    @contextmanager
    def traduire_contraintes(self, erreurs):
        yield


class HorlogeReglable:
    def __init__(self, instant: datetime) -> None:
        self.instant = instant

    def maintenant(self) -> datetime:
        return self.instant

    def avancer(self, **duree: float) -> None:
        self.instant += timedelta(**duree)


class JournalMemoire:
    def __init__(self) -> None:
        self.evenements: list[tuple[str, dict]] = []

    def evenement(self, nom: str, **champs) -> None:
        self.evenements.append((nom, champs))

    def noms(self) -> list[str]:
        return [nom for nom, _ in self.evenements]


class DiffusionMemoire:
    def __init__(self) -> None:
        self.evenements: list[dict] = []

    def publier(self, evenement: dict) -> None:
        self.evenements.append(evenement)


class HacheurClair:
    """Hachage factice et instantané : les tests portent sur la logique."""

    def hacher(self, mot_de_passe: str) -> str:
        return f"h:{mot_de_passe}"

    def verifier(self, empreinte: str, mot_de_passe: str) -> bool:
        return empreinte == f"h:{mot_de_passe}"


PARAMETRES = ParametresMetier(
    fuseau=PARIS, jours_ouverture=frozenset(range(5)), horizon_jours=60,
    duree_max_etudiant=timedelta(hours=2), description_longueur_max=2000,
    export_periode_max_jours=366, connexion_essais_libres=3,
    connexion_delai_initial=timedelta(seconds=1), connexion_delai_max=timedelta(minutes=15),
    duree_session=timedelta(hours=12),
)


# Comptes de démonstration (mêmes logins que db/seed.sql).
LOGIN_PAR_ROLE = {Role.ETUDIANT: "etud", Role.ENSEIGNANT: "prof", Role.GESTIONNAIRE: "gest"}
NOM_COMPLET = {"etud": "Étudiant", "prof": "Professeur", "gest": "Gestionnaire"}


@dataclass
class Application:
    """Services câblés sur des dépôts en mémoire, plus un jeu de données."""

    memoire: Memoire
    horloge: HorlogeReglable
    transaction: FausseTransaction
    journal: JournalMemoire
    journal_securite: JournalMemoire
    diffusion: DiffusionMemoire
    auth: ServiceAuthentification
    reservations: ServiceReservations
    salles: ServiceSalles
    fermetures: ServiceFermetures
    planning: ServicePlanning
    utilisateurs: ServiceUtilisateurs

    def personne(self, role: Role, login: str | None = None) -> Utilisateur:
        """Compte de test : etud@iut.fr, prof@iut.fr ou gest@iut.fr selon le rôle
        (« etud2 » pour un deuxième étudiant)."""
        login = login or LOGIN_PAR_ROLE[role]
        utilisateur = Utilisateur(email=f"{login}@iut.fr", nom="IUT",
                                  prenom=NOM_COMPLET[login.rstrip("0123456789")],
                                  role=role, mot_de_passe="h:motdepasse-correct")
        self.memoire.utilisateurs.append(utilisateur)
        return utilisateur

    def salle(self, code: str = "D101", **champs) -> Salle:
        batiment = self.memoire.batiments[0]
        salle = Salle(code=code, batiment_id=batiment.id, **champs)
        self.memoire.salles.append(salle)
        return salle


def application(instant: datetime | None = None) -> Application:
    memoire = Memoire(batiments=[Batiment("D")])
    horloge = HorlogeReglable(instant or a(8).replace(minute=30))
    transaction = FausseTransaction()
    journal, journal_securite, diffusion = JournalMemoire(), JournalMemoire(), DiffusionMemoire()
    socle = Socle(transaction=transaction, horloge=horloge, parametres=PARAMETRES,
                  journal=journal)
    publication = PublicationPlanning(diffusion, PARIS)
    utilisateurs, salles = DepotUtilisateurs(memoire), DepotSalles(memoire)
    reservations, fermetures = DepotReservations(memoire), DepotFermetures(memoire)
    return Application(
        memoire=memoire, horloge=horloge, transaction=transaction, journal=journal,
        journal_securite=journal_securite, diffusion=diffusion,
        auth=ServiceAuthentification(socle, utilisateurs=utilisateurs,
                                     sessions=DepotSessions(memoire),
                                     verrous=DepotVerrous(memoire), hacheur=HacheurClair(),
                                     journal_securite=journal_securite),
        reservations=ServiceReservations(socle, reservations=reservations, salles=salles,
                                         fermetures=fermetures, utilisateurs=utilisateurs,
                                         publication=publication),
        salles=ServiceSalles(socle, salles=salles, batiments=DepotBatiments(memoire),
                             reservations=reservations, publication=publication),
        fermetures=ServiceFermetures(socle, fermetures=fermetures, salles=salles,
                                     reservations=reservations, publication=publication),
        planning=ServicePlanning(PARAMETRES, salles=salles, reservations=reservations,
                                 fermetures=fermetures),
        utilisateurs=ServiceUtilisateurs(socle, utilisateurs=utilisateurs,
                                         journal_securite=journal_securite),
    )
