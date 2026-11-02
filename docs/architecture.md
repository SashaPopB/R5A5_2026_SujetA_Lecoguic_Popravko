# Architecture

Schémas du système, du plus large au plus précis (niveaux « contexte » et « conteneurs » du
modèle C4, puis modèle de données et séquence d'un cas d'usage). Les diagrammes sont écrits
en Mermaid : GitLab les affiche directement, VS Code avec l'extension « Markdown Preview
Mermaid Support ».

## Contexte

```mermaid
flowchart LR
    E["Étudiant / enseignant<br/>consulte, réserve, annule"]
    G["Gestionnaire (secrétariat)<br/>salles, créneaux, rôles, historique, export"]
    S["Application de réservation de salles"]
    T["Tableur d'archivage<br/>(fichier CSV)"]
    E -->|navigateur, HTTPS| S
    G -->|navigateur, HTTPS| S
    S -->|export A-10| T
```

Hors périmètre : notifications par courriel, emploi du temps, matériel des salles.

## Conteneurs

```mermaid
flowchart LR
    subgraph Navigateur
        F["Front React + TypeScript<br/>(fichiers statiques)"]
    end
    subgraph Serveur
        N["nginx<br/>HTTPS, fichiers statiques, relais /api"]
        A["API Flask<br/>gunicorn, 1 processus multi-threadé"]
        L[("Journaux JSON<br/>console / logs/*.log")]
    end
    B[("PostgreSQL 16<br/>contraintes EXCLUDE")]
    F -->|"HTTP JSON, cookies httpOnly + X-CSRF-TOKEN"| N
    N -->|"SSE GET /api/evenements (sans tampon)"| F
    N --> A
    A -->|SQL| B
    A --> L
```

Front et API partagent la même origine : les cookies `SameSite=Strict` suffisent, aucun CORS.

## Couches de l'API

```mermaid
flowchart TB
    R["api/routes : contrôleurs<br/>DTO pydantic, rôle, code HTTP"]
    S["services : cas d'usage"]
    P["services/ports.py : contrats (Protocol)"]
    D["domaine : règles pures"]
    I["persistance (SQLAlchemy), temps_reel,<br/>journal, horloge, hachage"]
    C["composition.py : câblage au démarrage"]
    R --> S
    S --> D
    S --> P
    I -. implémente .-> P
    C --> S
    C --> I
```

Les flèches pleines sont des dépendances de code : elles vont toutes vers le domaine et les
contrats. Les services ne dépendent ni de Flask, ni de SQLAlchemy, ni de `logging` ; leurs
dépendances arrivent par le constructeur (`composition.py` en production, dépôts en mémoire
dans `tests/unitaires/faux.py`).

## Modèle de données

```mermaid
erDiagram
    UTILISATEUR ||--o{ RESERVATION : "réserve"
    UTILISATEUR ||--o{ RESERVATION : "annule (annulee_par)"
    UTILISATEUR ||--o{ SESSION_UTILISATEUR : "ouvre"
    UTILISATEUR ||--o{ FERMETURE : "décide (cree_par)"
    BATIMENT ||--o{ SALLE : "contient"
    SALLE ||--o{ RESERVATION : "accueille"
    SALLE ||--o{ FERMETURE : "est fermée pendant"
    UTILISATEUR {
        uuid id PK
        text email UK "en minuscules"
        text mot_de_passe "empreinte scrypt"
        enum role "etudiant, enseignant, gestionnaire"
    }
    SALLE {
        uuid id PK
        text code UK "insensible à la casse"
        int capacite
        time heure_ouverture
        time heure_fermeture
        enum etat "ouverte, fermee, retiree"
    }
    RESERVATION {
        uuid id PK
        timestamptz debut
        timestamptz fin
        text description "Markdown restreint"
        enum statut "active, annulee"
        timestamptz annulee_le
        text motif_annulation
    }
    FERMETURE {
        uuid id PK
        timestamptz debut
        timestamptz fin
        text motif
    }
    SESSION_UTILISATEUR {
        uuid id PK "porté par le JWT (sid)"
        timestamptz expire_le
        timestamptz revoquee_le
    }
    VERROU_CONNEXION {
        text email PK
        int echecs
        timestamptz bloque_jusqu_a
    }
```

Invariants tenus par la base (`db/schema.sql`), en plus du code : pas deux réservations
actives qui se chevauchent sur une salle, ni pour une même personne (`EXCLUDE USING gist`
sur `tstzrange`), pas deux fermetures qui se chevauchent, et une réservation terminée ou
annulée ne se modifie plus (déclencheur `reservation_historique_immuable`).

## Séquence : réserver, puis diffuser (A-02, A-03, A-04)

```mermaid
sequenceDiagram
    participant Alice as Navigateur d'Alice
    participant Bob as Navigateur de Bob
    participant API as API Flask
    participant BD as PostgreSQL
    Bob->>API: GET /api/evenements (EventSource, cookie)
    API-->>Bob: retry, connecte {reprise: initiale}
    Alice->>API: POST /api/reservations + X-CSRF-TOKEN
    API->>API: refus par défaut ok, rôle ok, DTO valide
    API->>BD: SELECT ... FOR UPDATE (personne, salle)
    API->>BD: chevauchements ? limite étudiant ?
    API->>BD: INSERT reservation (EXCLUDE en dernier rempart)
    API->>BD: COMMIT
    API-->>Alice: 201 Created
    API-->>Bob: id: e.42 / event: planning {salle_id, jours}
    Bob->>API: GET /api/planning?date=… (règles de visibilité)
    API-->>Bob: créneau pris, sans le nom d'Alice
```

Si la connexion de Bob tombe, le navigateur se reconnecte avec `Last-Event-ID: e.42` : les
événements suivants sont rejoués s'ils sont encore dans l'historique, sinon le message
`connecte` porte `reprise: impossible` et le front recharge le planning.
