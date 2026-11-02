# Fiche 03 : Format et destination de la journalisation

## Le problème

Quand quelque chose se passe mal, il faut pouvoir répondre sans reproduire le bug : quelle
requête a échoué, pourquoi, laquelle est lente, qui essaie d'accéder à ce qui lui est
refusé. En même temps, un fichier de logs est copié/sauvegardé : il ne doit contenir ni mot
de passe, ni jeton, ni adresse email.

Le serveur de destination est inconnu, donc aucune dépendance à un fournisseur.

## Les options

Format : texte libre (lisible, mais il faut une expression régulière pour en avoir une
durée), texte à séparateurs (fragile dès qu'une colonne change) et JSON, une ligne par
événement (lisible, filtrable avec `jq`, accepté tel quel par Loki ou Elasticsearch).

Destination : console seule (perdue à l'arrêt), fichiers avec
rotation, base de données (charge la base métier, et ne journalise plus rien quand elle
tombe), plateforme centralisée ou service cloud (coût, hébergement des données, inutile
sur un seul serveur).

## Notre choix

JSON Lines avec une liste fixe de champs : `horodatage`, `niveau`, `message`,
`id_requete`, `methode`, `route`, `chemin`, `statut`, `duree_ms`, `utilisateur`,
`exception`… Le message est un nom d'événement stable (`requete.traitee`,
`reservation.creee`, `connexion.echec`) : tout ce qu'on compte ou filtre est un champ.

Une ligne par requête, écrite au départ de la réponse, y compris pour les requêtes
refusées avant d'atteindre une route. Niveau tiré du statut : INFO pour un succès, WARNING
pour une erreur du client (dont 401, 403, 429), ERROR pour une erreur du serveur, dont la
pile d'appels part sur une ligne à part, reliée par `id_requete`.

Les événements métier passent par une interface `Journal` : le service nomme
l'événement, la configuration décide du niveau et de la destination.

Destination : la console, plus `logs/api.log` (rotation chaque nuit, 180 jours) et
`logs/erreurs.log` (erreurs seules, 365 jours). La CNIL recommande six mois à un an.

Jamais : mot de passe, jeton, adresse email (même en cas d'échec de connexion), corps de
requête. L'adresse IP n'est écrite que sur les refus, seul cas où elle sert.

## Ce que ça coûte

Pas de vue d'ensemble à plusieurs serveurs : il faudrait expédier les fichiers vers une
plateforme. Le format JSON est prêt pour ça.

Un seul processus doit écrire dans les fichiers : la rotation de Python n'est pas sûre
avec plusieurs processus. C'est déjà la contrainte du temps réel (fiche 02).

Mesurer chaque réponse a un piège : sur le flux temps réel, calculer la taille forçait
Flask à attendre la fin du flux, 15 minutes. Les réponses en flux ne sont plus mesurées.

Aucune alerte automatique : il reste à brancher une sonde sur `/api/sante` et une
surveillance des lignes ERROR.
