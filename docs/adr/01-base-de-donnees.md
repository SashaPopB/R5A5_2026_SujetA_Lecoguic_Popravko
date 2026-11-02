# Fiche 01 : Base de données

## Le problème

Deux exigences du sujet pèsent plus que les autres :

Un créneau réservé n'est plus proposé. Problème si deux étudiants valident la même salle à
la même seconde : un contrôle « je lis, puis j'écris » laisse passer les deux.

Retrouver qui a réservé ou annulé, et quand. Si une réservation peut être supprimée ou
réécrite, l'historique ne prouve plus rien.

## Les options

| Option | Pour | Contre |
|---|---|---|
| SQLite | Aucun serveur, un fichier | Un seul écrivain à la fois ; aucune contrainte sur des intervalles : le non-chevauchement dépendrait du code |
| MySQL / MariaDB | Très répandu | Pas de contrainte d'exclusion sur des plages horaires : verrou applicatif ou déclencheur maison |
| MongoDB | Schéma souple | Nos données sont relationnelles (salle, personne, réservation) ; pas de contrainte entre documents |
| PostgreSQL | Contraintes d'exclusion, types intervalle, horodatages avec fuseau | Un serveur à installer et à faire tourner |

## Notre choix : PostgreSQL

Le chevauchement est refusé par la base elle-même : une contrainte
`EXCLUDE USING gist(salle_id WITH =, tstzrange(debut, fin, '[)') WITH &&)` sur les
réservations actives. On l'a vérifié dans `psql` : quand deux insertions se chevauchent, la
seconde est rejetée, et l'API renvoie une 409. Même chose pour les personnes qui veulent
occuper deux salles à la fois. Le code vérifie aussi avant d'écrire, pour donner un message
clair, mais la base reste le dernier rempart.

L'historique ne se réécrit pas : un déclencheur refuse la suppression d'une réservation et
n'autorise qu'une modification, son annulation (date, auteur, motif).

## Ce que ça coûte

Un serveur PostgreSQL à installer (extension `btree_gist` fournie avec). Pour ne pas en
faire un obstacle, `./demarrer.sh` crée l'utilisateur et les bases.

Du SQL propre à PostgreSQL (`EXCLUDE`, `tstzrange`) : changer de moteur obligerait à
réécrire ces garanties dans le code, avec le risque de concurrence qu'on voulait éviter.

Des tests plus lourds : les tests de droits tournent sur une vraie base
(`sae_salles_test`) ; une base en mémoire ne vérifierait pas ces contraintes.

Pas d'outil de migration : `db/schema.sql` est rejoué en entier.
