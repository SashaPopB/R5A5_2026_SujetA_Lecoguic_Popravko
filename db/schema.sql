-- =====================================================================
--  SAE R5A5 - Sujet A : Réservation de salles
--  Schéma PostgreSQL (version >= 13 : gen_random_uuid() natif,
--  btree_gist installable par le propriétaire de la base).
--
--  Ce fichier est la source de vérité du modèle de données. Il est
--  appliqué par `flask --app wsgi init-db` ou à la main (psql / pgAdmin).
--  Il est idempotent : il supprime puis recrée tout.
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS btree_gist;

DROP TABLE IF EXISTS fermeture           CASCADE;
DROP TABLE IF EXISTS reservation         CASCADE;
DROP TABLE IF EXISTS salle               CASCADE;
DROP TABLE IF EXISTS batiment            CASCADE;
DROP TABLE IF EXISTS session_utilisateur CASCADE;
DROP TABLE IF EXISTS verrou_connexion    CASCADE;
DROP TABLE IF EXISTS utilisateur         CASCADE;
DROP FUNCTION IF EXISTS reservation_proteger_historique() CASCADE;
DROP TYPE IF EXISTS statut_reservation;
DROP TYPE IF EXISTS etat_salle;
DROP TYPE IF EXISTS role_utilisateur;

-- Vocabulaire du sujet : étudiant, enseignant, gestionnaire.
CREATE TYPE role_utilisateur   AS ENUM ('etudiant', 'enseignant', 'gestionnaire');
-- A-07 : le gestionnaire ouvre, ferme ou retire une salle.
CREATE TYPE etat_salle         AS ENUM ('ouverte', 'fermee', 'retiree');
-- Une réservation ne disparaît jamais : elle est active ou annulée (A-08).
CREATE TYPE statut_reservation AS ENUM ('active', 'annulee');

-- ------------------------------------------------------------- comptes
CREATE TABLE utilisateur (
    id           UUID             PRIMARY KEY DEFAULT gen_random_uuid(),
    email        TEXT             NOT NULL UNIQUE,
    mot_de_passe TEXT             NOT NULL,                 -- hash Werkzeug (scrypt)
    nom          TEXT             NOT NULL CHECK (btrim(nom) <> ''),
    prenom       TEXT             NOT NULL CHECK (btrim(prenom) <> ''),
    role         role_utilisateur NOT NULL DEFAULT 'etudiant',
    cree_le      TIMESTAMPTZ      NOT NULL DEFAULT now(),
    CONSTRAINT utilisateur_email_valide
        CHECK (email = lower(email) AND position('@' IN email) > 1)
);

-- Une ligne par connexion. Le jeton de rafraîchissement porte l'id de sa
-- session : révoquer la session (déconnexion) invalide immédiatement les
-- deux jetons, sans attendre leur expiration.
CREATE TABLE session_utilisateur (
    id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    utilisateur_id UUID        NOT NULL REFERENCES utilisateur(id) ON DELETE CASCADE,
    cree_le        TIMESTAMPTZ NOT NULL DEFAULT now(),
    expire_le      TIMESTAMPTZ NOT NULL,
    revoquee_le    TIMESTAMPTZ,
    CHECK (expire_le > cree_le)
);
CREATE INDEX idx_session_utilisateur ON session_utilisateur (utilisateur_id);

-- Limitation des essais de connexion (« max retry + jail »). La clé est
-- l'adresse saisie, qu'un compte existe ou non : la réponse est identique
-- dans les deux cas, ce qui évite de révéler quels comptes existent.
CREATE TABLE verrou_connexion (
    email          TEXT        PRIMARY KEY,
    echecs         INT         NOT NULL DEFAULT 0 CHECK (echecs >= 0),
    dernier_echec  TIMESTAMPTZ NOT NULL DEFAULT now(),
    bloque_jusqu_a TIMESTAMPTZ
);

-- ---------------------------------------------------------- patrimoine
CREATE TABLE batiment (
    id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    nom  TEXT NOT NULL
);

CREATE TABLE salle (
    id              UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    code            TEXT       NOT NULL,                     -- ex. D101
    nom             TEXT,
    batiment_id     UUID       NOT NULL REFERENCES batiment(id) ON DELETE RESTRICT,
    etage           INT        NOT NULL DEFAULT 0,
    capacite        INT        NOT NULL CHECK (capacite > 0),
    -- Horaires d'ouverture : la grille du planning est horaire, d'où des
    -- heures pleines entre 06:00 et 23:00.
    heure_ouverture TIME       NOT NULL DEFAULT '08:00',
    heure_fermeture TIME       NOT NULL DEFAULT '20:00',
    etat            etat_salle NOT NULL DEFAULT 'ouverte',
    CONSTRAINT salle_horaires_coherents CHECK (
        heure_fermeture > heure_ouverture
        AND heure_ouverture >= '06:00' AND heure_fermeture <= '23:00'
        AND date_part('minute', heure_ouverture) = 0
        AND date_part('minute', heure_fermeture) = 0
    )
);
-- Unicité du code sans tenir compte de la casse (d101 = D101).
CREATE UNIQUE INDEX salle_code_unique ON salle (upper(code));

-- ---------------------------------------------------------- réservations
CREATE TABLE reservation (
    id                UUID               PRIMARY KEY DEFAULT gen_random_uuid(),
    salle_id          UUID               NOT NULL REFERENCES salle(id)       ON DELETE RESTRICT,
    utilisateur_id    UUID               NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
    debut             TIMESTAMPTZ        NOT NULL,
    fin               TIMESTAMPTZ        NOT NULL,
    -- Texte mis en forme (A-02), stocké au format Markdown restreint :
    -- aucune balise HTML n'est jamais interprétée par le navigateur.
    description       TEXT               NOT NULL
                      CHECK (length(btrim(description)) BETWEEN 1 AND 2000),
    statut            statut_reservation NOT NULL DEFAULT 'active',
    cree_le           TIMESTAMPTZ        NOT NULL DEFAULT now(),
    annulee_le        TIMESTAMPTZ,
    annulee_par       UUID               REFERENCES utilisateur(id) ON DELETE RESTRICT,
    motif_annulation  TEXT               CHECK (length(motif_annulation) <= 200),

    CONSTRAINT reservation_duree CHECK (fin > debut),
    CONSTRAINT reservation_annulation_coherente CHECK (
        (statut = 'annulee') = (annulee_le IS NOT NULL AND annulee_par IS NOT NULL)
    ),

    -- A-03 : deux réservations actives ne peuvent pas se chevaucher dans une
    -- même salle. Un SELECT de vérification suivi d'un INSERT laisserait
    -- passer deux requêtes simultanées ; la contrainte EXCLUDE (index GiST)
    -- ferme cette fenêtre au niveau du moteur.
    CONSTRAINT reservation_sans_chevauchement_salle
        EXCLUDE USING gist (
            salle_id                    WITH =,
            tstzrange(debut, fin, '[)') WITH &&
        ) WHERE (statut = 'active'),

    -- Une personne réserve « pour elle-même » : elle ne peut pas occuper
    -- deux salles en même temps.
    CONSTRAINT reservation_sans_chevauchement_utilisateur
        EXCLUDE USING gist (
            utilisateur_id              WITH =,
            tstzrange(debut, fin, '[)') WITH &&
        ) WHERE (statut = 'active')
);

CREATE INDEX idx_reservation_debut       ON reservation (debut);
CREATE INDEX idx_reservation_utilisateur ON reservation (utilisateur_id, debut DESC);

-- A-08 : l'historique (qui a réservé, qui a annulé, quand) vit dans la
-- réservation elle-même. On le protège : une réservation ne se supprime
-- pas et la seule modification permise est l'annulation d'une réservation
-- active. Même un bug applicatif ne peut donc pas réécrire l'historique.
CREATE FUNCTION reservation_proteger_historique() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Une réservation ne se supprime pas, elle s''annule'
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF OLD.statut = 'annulee' THEN
        RAISE EXCEPTION 'Une réservation annulée ne peut plus être modifiée'
            USING ERRCODE = 'restrict_violation';
    END IF;

    IF NEW.salle_id       IS DISTINCT FROM OLD.salle_id
       OR NEW.utilisateur_id IS DISTINCT FROM OLD.utilisateur_id
       OR NEW.debut       IS DISTINCT FROM OLD.debut
       OR NEW.fin         IS DISTINCT FROM OLD.fin
       OR NEW.description IS DISTINCT FROM OLD.description
       OR NEW.cree_le     IS DISTINCT FROM OLD.cree_le
       OR NEW.id          IS DISTINCT FROM OLD.id THEN
        RAISE EXCEPTION 'Seule l''annulation d''une réservation est autorisée'
            USING ERRCODE = 'restrict_violation';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER reservation_historique_immuable
    BEFORE UPDATE OR DELETE ON reservation
    FOR EACH ROW EXECUTE FUNCTION reservation_proteger_historique();

-- -------------------------------------------------- créneaux fermés (A-07)
-- Le gestionnaire ferme une plage horaire d'une salle (travaux, examen...).
CREATE TABLE fermeture (
    id        UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    salle_id  UUID        NOT NULL REFERENCES salle(id) ON DELETE CASCADE,
    debut     TIMESTAMPTZ NOT NULL,
    fin       TIMESTAMPTZ NOT NULL,
    motif     TEXT        NOT NULL CHECK (length(btrim(motif)) BETWEEN 1 AND 200),
    cree_par  UUID        NOT NULL REFERENCES utilisateur(id) ON DELETE RESTRICT,
    cree_le   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fermeture_duree CHECK (fin > debut),
    CONSTRAINT fermeture_sans_chevauchement
        EXCLUDE USING gist (
            salle_id                    WITH =,
            tstzrange(debut, fin, '[)') WITH &&
        )
);
