# Fiche 02 : Mécanisme de temps réel

## Le problème

Quand quelqu'un réserve ou annule, ceux qui regardent le planning le voient sans recharger
la page. On laisse quand même un retard acceptable de quelques secondes.

Les données ne vont que dans un sens, du serveur vers les navigateurs : réserver ou annuler
reste une requête HTTP ordinaire, avec sa validation, ses droits et son code de statut.
Ordre de grandeur : ~10 salles et quelques dizaines de personnes connectées max.

## Les options

| Option | Pour | Contre |
|---|---|---|
| Polling (requête toutes les N s) | Rien à installer | Retard de N/2 s en moyenne, une requête par client toutes les N s même sans changement |
| Server-Sent Events | HTTP ordinaire, `EventSource` natif, reconnexion automatique, cookie envoyé seul | Un seul sens, un thread occupé par client avec Flask |
| WebSocket / Socket.IO | Deux sens, latence minimale | Bibliothèques des deux côtés, configuration du proxy ; le deuxième sens ne nous sert à rien |

## Notre choix : Server-Sent Events

Le navigateur ouvre `GET /api/evenements`. Après chaque modification validée en base,
l'API publie un événement minimal : type, salle, jours touchés. Pas de nom, pas de
description : le navigateur recharge le planning par l'API, qui applique les règles de
visibilité. Le canal ne peut rien divulguer.

Reprise après coupure : chaque événement porte un identifiant et les 500 derniers sont
gardés. À la reconnexion, le navigateur envoie le dernier reçu. L'API rejoue ce qui a été
manqué, ou demande de tout recharger si c'est trop ancien. La base reste toujours la
référence.

Un message vide part toutes les 15 s pour que les proxys ne coupent pas la connexion. Le flux
se ferme quand la session expire, ce qui revérifie les droits à chaque reconnexion.

Un bouton « Rafraîchir » reste dans le planning : si le direct tombe, on peut recharger.

## Ce que ça coûte

Un seul processus : la liste des connectés vit en mémoire.

Un thread par onglet ouvert : gunicorn tourne avec 64 threads, assez pour notre public.
nginx doit transmettre le flux sans le mettre en tampon (`docs/deploiement.md`).

Une connexion longue casse des habitudes prises avec les requêtes courtes. Nous l'avons
appris en lançant les tests de droits : le journal mesurait la taille de chaque réponse, et
pour mesurer le flux, Flask attendait qu'il se termine, c'est-à-dire 15 minutes. Le
planning ne se mettait donc jamais à jour. Corrigé, avec un test qui échouait avant.

Chaque événement provoque un rechargement du planning chez ceux qui affichent ce jour-là.
C'est négligeable à notre échelle, mais si le nombre d'utilisateurs était multiplié par
cent, ça pourrait sauter.
