-- =====================================================================
--  Données de démonstration (à appliquer APRÈS schema.sql).
--  Les dates sont calculées à partir de la semaine courante : le jeu de
--  données reste parlant quel que soit le jour où on l'installe.
--
--  Comptes (mot de passe commun : motdepasse)
--    gest@iut.fr  -> gestionnaire (secrétariat)
--    prof@iut.fr  -> enseignant
--    etud@iut.fr  -> étudiant
-- =====================================================================

-- Hash Werkzeug (scrypt) de « motdepasse ».
INSERT INTO utilisateur (email, mot_de_passe, nom, prenom, role) VALUES
    ('gest@iut.fr', 'scrypt:32768:8:1$O18DsjXnSdNtr8MY$c47eb9c70d4e57c97b706c121b99fe97a9f141161ec8dba111f4f4529e94f956e6bc009ddfe517be5befbbd1c41cb96c85c3c37ebe5a565ca7a335015b95a1fb', 'IUT', 'Gestionnaire', 'gestionnaire'),
    ('prof@iut.fr', 'scrypt:32768:8:1$O18DsjXnSdNtr8MY$c47eb9c70d4e57c97b706c121b99fe97a9f141161ec8dba111f4f4529e94f956e6bc009ddfe517be5befbbd1c41cb96c85c3c37ebe5a565ca7a335015b95a1fb', 'IUT', 'Professeur',   'enseignant'),
    ('etud@iut.fr', 'scrypt:32768:8:1$O18DsjXnSdNtr8MY$c47eb9c70d4e57c97b706c121b99fe97a9f141161ec8dba111f4f4529e94f956e6bc009ddfe517be5befbbd1c41cb96c85c3c37ebe5a565ca7a335015b95a1fb', 'IUT', 'Étudiant',     'etudiant');

INSERT INTO batiment (code, nom) VALUES
    ('B', 'Bâtiment B'),
    ('D', 'Bâtiment D');

-- Salles de travail (sujet A).
INSERT INTO salle (code, nom, batiment_id, etage, capacite, heure_ouverture, heure_fermeture, etat)
SELECT v.code, NULL, b.id, v.etage, v.capacite, v.ouverture::time, v.fermeture::time, 'ouverte'
FROM (VALUES
    ('D101', 'D', 1,  8, '08:00', '20:00'),
    ('D102', 'D', 1,  8, '08:00', '20:00'),
    ('D103', 'D', 1, 12, '08:00', '20:00'),
    ('D201', 'D', 2, 20, '08:00', '20:00'),
    ('D202', 'D', 2, 20, '08:00', '19:00'),
    ('B114', 'B', 1, 24, '08:00', '18:00')
) AS v(code, batiment, etage, capacite, ouverture, fermeture)
JOIN batiment b ON b.code = v.batiment;

-- Réservations de la semaine courante et de la suivante (jour 0 = lundi).
-- Les heures sont exprimées à l'heure de Paris, quel que soit le fuseau du
-- serveur de base de données.
DO $$
DECLARE
    lundi DATE := CURRENT_DATE - (EXTRACT(ISODOW FROM CURRENT_DATE)::INT - 1);
BEGIN
    INSERT INTO reservation (salle_id, utilisateur_id, debut, fin, description, statut,
                             cree_le, annulee_le, annulee_par, motif_annulation)
    SELECT s.id,
           u.id,
           ((lundi + v.jour) + v.h_debut::time) AT TIME ZONE 'Europe/Paris',
           ((lundi + v.jour) + v.h_fin::time)   AT TIME ZONE 'Europe/Paris',
           v.description,
           v.statut::statut_reservation,
           ((lundi + v.jour) + v.h_debut::time) AT TIME ZONE 'Europe/Paris' - interval '2 days',
           CASE WHEN v.statut = 'annulee'
                THEN ((lundi + v.jour) + v.h_debut::time) AT TIME ZONE 'Europe/Paris' - interval '1 day'
           END,
           a.id,
           v.motif_annulation
    FROM (VALUES
        ('D201',  0, '10:00', '12:00', E'Rattrapage **R3.05 Réseaux** pour le groupe B',
         'prof@iut.fr', 'active',  NULL, NULL),
        ('D101',  0, '14:00', '16:00', E'Projet SAE : *préparation de la démo*\n- maquettes\n- répétition',
         'etud@iut.fr', 'active',  NULL, NULL),
        ('D103',  1, '09:00', '11:00', E'Révisions BDD, sujet sur [Moodle](https://moodle.example.org/course/42)',
         'etud@iut.fr', 'active',  NULL, NULL),
        ('D102',  1, '13:00', '14:00', E'Point binôme',
         'etud@iut.fr', 'annulee', 'etud@iut.fr', NULL),
        ('B114',  2, '08:00', '12:00', E'Suivi des projets tuteurés (enseignant : pas de limite de durée)',
         'prof@iut.fr', 'active',  NULL, NULL),
        ('D102',  2, '10:00', '12:00', E'Atelier Git',
         'etud@iut.fr', 'annulee', 'gest@iut.fr', 'Salle réquisitionnée pour un jury'),
        ('D101',  3, '16:00', '18:00', E'Rédaction du rapport\n1. plan\n2. relecture',
         'etud@iut.fr', 'active',  NULL, NULL),
        ('D202',  4, '09:00', '10:00', E'Entretien de stage (visio)',
         'etud@iut.fr', 'active',  NULL, NULL),
        ('D201',  7, '10:00', '12:00', E'Projet SAE : intégration',
         'etud@iut.fr', 'active',  NULL, NULL),
        ('D103',  8, '14:00', '16:00', E'Préparation **oral d''anglais**',
         'etud@iut.fr', 'active',  NULL, NULL),
        ('D201',  9, '13:00', '17:00', E'Soutenances blanches',
         'prof@iut.fr', 'active',  NULL, NULL),
        ('D101', 10, '09:00', '11:00', E'Projet SAE : tests',
         'etud@iut.fr', 'active',  NULL, NULL)
    ) AS v(salle_code, jour, h_debut, h_fin, description, email, statut, annule_par, motif_annulation)
    JOIN salle s            ON s.code = v.salle_code
    JOIN utilisateur u      ON u.email = v.email
    LEFT JOIN utilisateur a ON a.email = v.annule_par;

    INSERT INTO fermeture (salle_id, debut, fin, motif, cree_par)
    SELECT s.id,
           ((lundi + 8) + time '08:00') AT TIME ZONE 'Europe/Paris',
           ((lundi + 8) + time '12:00') AT TIME ZONE 'Europe/Paris',
           'Maintenance du vidéoprojecteur',
           g.id
    FROM salle s, utilisateur g
    WHERE s.code = 'D102' AND g.email = 'gest@iut.fr';
END $$;
