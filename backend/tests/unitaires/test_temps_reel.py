"""Diffuseur d'événements temps réel (A-04) : diffusion, historique et
reprise après coupure (Last-Event-ID), journal des connexions."""
import json
import logging
import re

from app.temps_reel import DiffuseurEvenements, ReglagesFlux, flux_sse, formater_sse


def _donnees(message: str) -> dict:
    ligne = next(texte for texte in message.splitlines() if texte.startswith("data: "))
    return json.loads(ligne.removeprefix("data: "))


def _identifiant(message: str) -> str:
    return re.search(r"^id: (.+)$", message, re.MULTILINE).group(1)


def _vider(file) -> list[str]:
    messages = []
    while not file.empty():
        messages.append(file.get_nowait())
    return messages


def test_format_sse():
    message = formater_sse({"type": "planning"}, identifiant="a1.7")
    assert message == 'id: a1.7\nevent: planning\ndata: {"type":"planning"}\n\n'


def test_chaque_abonne_recoit_l_evenement_avec_un_identifiant():
    diffuseur = DiffuseurEvenements()
    abonnements = [diffuseur.abonner(), diffuseur.abonner()]
    diffuseur.publier({"type": "planning", "jours": ["2026-11-02"]})
    for abonnement in abonnements:
        assert abonnement.reprise == "initiale"
        message = abonnement.file.get_nowait()
        assert _donnees(message)["jours"] == ["2026-11-02"]
        assert _identifiant(message)


def test_reprise_rejoue_les_evenements_manques():
    diffuseur = DiffuseurEvenements()
    premier = diffuseur.abonner()
    diffuseur.publier({"type": "planning", "n": 1})
    dernier_recu = _identifiant(premier.file.get_nowait())
    diffuseur.desabonner(premier.file)  # coupure réseau
    diffuseur.publier({"type": "planning", "n": 2})
    diffuseur.publier({"type": "planning", "n": 3})

    reprise = diffuseur.abonner(dernier_recu)
    assert reprise.reprise == "complete"
    assert [_donnees(m)["n"] for m in _vider(reprise.file)] == [2, 3]


def test_reprise_sans_evenement_manque():
    diffuseur = DiffuseurEvenements()
    abonnement = diffuseur.abonner()
    diffuseur.publier({"type": "planning"})
    dernier = _identifiant(abonnement.file.get_nowait())
    assert diffuseur.abonner(dernier).reprise == "complete"


def test_reprise_impossible_si_l_historique_est_depasse():
    diffuseur = DiffuseurEvenements(taille_historique=2)
    abonnement = diffuseur.abonner()
    diffuseur.publier({"type": "planning", "n": 1})
    dernier = _identifiant(abonnement.file.get_nowait())
    for numero in range(2, 5):  # l'événement 2 sort de l'historique
        diffuseur.publier({"type": "planning", "n": numero})
    reprise = diffuseur.abonner(dernier)
    assert reprise.reprise == "impossible"
    assert reprise.file.empty()


def test_reprise_impossible_apres_un_redemarrage_du_serveur():
    ancien = DiffuseurEvenements()
    abonnement = ancien.abonner()
    ancien.publier({"type": "planning"})
    dernier = _identifiant(abonnement.file.get_nowait())
    nouveau = DiffuseurEvenements()  # autre processus, autre époque
    assert nouveau.abonner(dernier).reprise == "impossible"
    assert nouveau.abonner("n-importe-quoi").reprise == "impossible"


def test_un_client_lent_est_resynchronise_sans_bloquer_les_autres():
    diffuseur = DiffuseurEvenements(taille_file=2)
    lent, rapide = diffuseur.abonner(), diffuseur.abonner()
    for numero in range(3):
        diffuseur.publier({"type": "planning", "n": numero})
        rapide.file.get_nowait()
    assert _donnees(lent.file.get_nowait())["type"] == "resynchronisation"


def test_le_flux_se_ferme_a_l_expiration_desabonne_et_journalise(caplog):
    diffuseur = DiffuseurEvenements()
    abonnement = diffuseur.abonner()
    instants = iter([0.0, 0.0, 10.0, 10.0])
    reglages = ReglagesFlux(pulsation=1, fin_validite=5.0, retry_ms=3000,
                            horloge=lambda: next(instants))
    with caplog.at_level(logging.INFO, logger="sae.temps_reel"):
        flux = flux_sse(abonnement, diffuseur, reglages, {"utilisateur": "u1"})
        assert next(flux) == "retry: 3000\n\n"
        connecte = next(flux)
        assert _donnees(connecte) == {"type": "connecte", "reprise": "initiale"}
        abonnement.file.put_nowait(formater_sse({"type": "planning"}))
        assert "planning" in next(flux)
        assert list(flux) == []  # jeton expiré : fin du flux
    assert diffuseur.nombre_abonnes == 0
    ouvert, ferme = (r for r in caplog.records if r.name == "sae.temps_reel")
    assert ouvert.getMessage() == "flux.ouvert" and ouvert.utilisateur == "u1"
    assert ferme.getMessage() == "flux.ferme"
    assert (ferme.motif, ferme.evenements_envoyes, ferme.connexions_actives) == \
        ("jeton_expire", 1, 0)


def test_un_client_parti_est_retire_de_la_liste(caplog):
    diffuseur = DiffuseurEvenements()
    abonnement = diffuseur.abonner()
    reglages = ReglagesFlux(pulsation=1, fin_validite=1e12, retry_ms=3000)
    with caplog.at_level(logging.INFO, logger="sae.temps_reel"):
        flux = flux_sse(abonnement, diffuseur, reglages, {})
        next(flux)
        flux.close()  # le serveur WSGI ferme le générateur quand l'écriture échoue
    assert diffuseur.nombre_abonnes == 0
    assert caplog.records[-1].motif == "client_parti"
