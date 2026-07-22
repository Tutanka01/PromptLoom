# PromptLoom

**Turn prompts into educational videos.**

[![CI](https://github.com/Tutanka01/PromptLoom/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/Tutanka01/PromptLoom/actions/workflows/ci.yml)
[![python](https://img.shields.io/badge/python-3.11-blue)](https://www.python.org/)

PromptLoom transforme un prompt en vidéo éducative complète : recherche,
scénario, narration multilingue, scènes animées, voix, rendu, assemblage et
contrôles qualité. Le tout est exposé par une API asynchrone et reproductible,
et pilotable depuis une interface web — **Studio** — livrée avec la plateforme.

[Commencer ici](docs/START_HERE.md) · [Créer sa première vidéo](docs/FIRST_VIDEO.md) ·
[Studio](apps/studio/README.md) ·
[Référence API](apps/video-api/docs/api-reference.md) ·
[Architecture](apps/video-api/docs/architecture.md)

## Exemples générés avec PromptLoom

Clique sur une image pour ouvrir la vidéo MP4 correspondante.

| Français | Español |
| --- | --- |
| [![Exemple PromptLoom en français](docs/assets/examples/exemple-francais.png)](videos/examples/fran%C3%A7ais-exemple.mp4) | [![Ejemplo de PromptLoom en español](docs/assets/examples/exemple-espagnol.png)](videos/examples/espagnol-exemple.mp4) |
| **Pédagogie orientée projet** — 4 min 27, 1080p30, narration française. [Regarder la vidéo](videos/examples/fran%C3%A7ais-exemple.mp4) | **Pedagogía orientada a proyectos** — 5 min 30, 1080p30, narración española. [Ver el vídeo](videos/examples/espagnol-exemple.mp4) |

## Ce que fait la plateforme

```text
prompt utilisateur
  -> recherche et sources optionnelles
  -> blueprint pédagogique validé
  -> narration + scènes + beats visuels
  -> voix locale, distante ou compatible OpenAI
  -> rendu Manim ou Remotion
  -> assemblage ffmpeg
  -> ffprobe + freezedetect + snapshots + revue optionnelle
  -> MP4 téléchargeable
```

PromptLoom sait notamment produire une vidéo dans une langue différente de
celle du prompt, générer un même contenu dans plusieurs langues et réparer un
job lorsque la génération ou le rendu échoue.

- **Suivi en temps réel** — l'API propose, pour chaque job, un flux Server-Sent
  Events (SSE) qui transmet l'état courant puis les changements d'étape. Le
  Studio maintient aussi un polling régulier si le flux est indisponible.
- **Progression détaillée** — le Studio affiche les sous-étapes enregistrées
  par le worker : frames Remotion, scènes générées ou rendues et segments TTS.
  Le temps restant apparaît lorsque Remotion fournit cette estimation.
- **Réparations observables** — pendant une nouvelle tentative, le Studio
  affiche le numéro de la réparation et son dernier motif. L'API expose ces
  informations dans `attempt_number`, `max_attempts` et `last_repair_reason`.

## Où commencer ?

| Ton objectif | Parcours recommandé |
| --- | --- |
| Découvrir le résultat | Regarde les [deux exemples](#exemples-générés-avec-promptloom), puis lis [Comment ça marche](docs/START_HERE.md#le-modèle-mental-en-90-secondes). |
| Générer une première vidéo | Suis le tutoriel [Première vidéo](docs/FIRST_VIDEO.md), qui passe par le Studio. |
| Piloter la plateforme sans écrire de requête | Ouvre le [Studio](apps/studio/README.md) sur `http://localhost:3000`. |
| Intégrer l'API | Lis la [référence HTTP](apps/video-api/docs/api-reference.md) et le [contrat LLM](apps/video-api/docs/llm-contract.md). |
| Contribuer au code | Commence par le [guide développeur](apps/video-api/docs/developer-guide.md). |
| Déployer ou diagnostiquer | Utilise le [guide d'exploitation](apps/video-api/docs/operations.md). |
| Installer le TTS sur un GPU séparé | Consulte [`apps/tts-server`](apps/tts-server/README.md). |

## Studio, l'interface de production

**PromptLoom Studio** est une SPA React + TypeScript construite avec Vite et
Tailwind. Livrée dans le même `compose.yaml`, elle fournit une console de
production complète : formulaire adapté aux capacités réelles du serveur,
tableau de bord des jobs et batches multilingues, suivi en direct combinant SSE
et polling, lecteur vidéo, rapports et artefacts.

Depuis le tableau de bord, tu peux annuler un job actif, supprimer un job
terminal avec ses artefacts, supprimer en bloc les jobs échoués ou annulés
affichés, ou relancer un job individuel échoué ou annulé. La page d'un job
affiche aussi les compteurs du rendu et du TTS, le temps restant lorsqu'il est
connu, ainsi que le numéro et le motif de la dernière réparation.

Le service `studio` est disponible sur <http://localhost:3000> après
`make start`. Consulte le [guide du Studio](apps/studio/README.md) pour le lancer
seul, viser une autre API ou configurer l'authentification.

## Démarrage en cinq étapes

### 1. Prérequis

- Docker avec Docker Compose 2.20 ou plus récent;
- un endpoint LLM compatible OpenAI pour une vraie génération;
- suffisamment d'espace disque pour l'image worker, qui inclut les moteurs de
  rendu et les dépendances audio;
- un navigateur pour le Studio; `curl` et Python 3 seulement si tu préfères
  passer par l'API.

Le premier build est volontairement lourd. Les builds suivants réutilisent les
couches Docker tant que les manifestes de dépendances ne changent pas.

### 2. Configurer

```bash
cp apps/video-api/.env.example .env
```

Renseigne au minimum :

```text
OPENAI_BASE_URL=http://host.docker.internal:8000/v1
OPENAI_API_KEY=...
OPENAI_MODEL=...
```

Sans LLM, `VIDEO_API_FAKE_LLM=1` permet de vérifier le pipeline avec un
blueprint déterministe. Ce mode évite l'appel LLM, mais la voix et le rendu
restent de vraies étapes.

Choisis aussi ton moteur vocal — le fichier d'exemple part sur `chatterbox`,
qui ne parle qu'anglais et reste lent sur CPU :

```text
VIDEO_API_VOICE_ENGINE=kokoro   # EN/FR, ~5x temps réel sur CPU
```

Voir [Choisir son moteur vocal](#choisir-son-moteur-vocal) pour les autres
langues.

### 3. Vérifier et lancer

```bash
make doctor
make start
make health
```

Équivalent sans `make` :

```bash
docker compose config --quiet
docker compose up --build -d
curl http://localhost:8080/healthz
```

### 4. Créer un premier job

Ouvre le **Studio** sur <http://localhost:3000> : il est démarré par `make start`
au même titre que l'API. Le formulaire se construit à partir des capacités
réelles du serveur (`GET /v1/capabilities`), affiche la progression étape par
étape via le flux SSE et le polling, puis le lecteur, le rapport et les
artefacts. Renseigne le sujet, choisis `draft` et 60 secondes, et lance.

L'équivalent en API — le profil `draft` et une cible de 60 secondes réduisent le
temps de cette première boucle :

```bash
RESPONSE=$(curl -sS -X POST http://localhost:8080/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Explain visually why derivatives measure instantaneous change",
    "theme": "math",
    "language": "en",
    "target_duration_seconds": 60,
    "quality_profile": "draft"
  }')

echo "$RESPONSE"
JOB_ID=$(printf '%s' "$RESPONSE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')
echo "Job: $JOB_ID"
```

Suivre le job :

```bash
curl "http://localhost:8080/v1/videos/$JOB_ID"
docker compose logs -f worker
```

### 5. Télécharger le résultat

Le Studio propose le MP4, le rapport et les artefacts sur la page du job. En
ligne de commande, quand `status` vaut `completed` :

```bash
curl -L "http://localhost:8080/v1/videos/$JOB_ID/download" -o promptloom-demo.mp4
curl "http://localhost:8080/v1/videos/$JOB_ID/report"
```

Le tutoriel [Première vidéo](docs/FIRST_VIDEO.md) explique chaque étape, les
choix de moteur et les erreurs fréquentes.

## Choisir son moteur vocal

Le moteur TTS est un choix de déploiement (`.env`); la *voix*, elle, se choisit
par requête (`GET /v1/voices`, champ `voice`, sélecteur dans le Studio). Ce
choix décide des langues disponibles et du temps d'attente de chaque job.

| `VIDEO_API_VOICE_ENGINE` | Langues | Coût / vitesse | Voix sélectionnable |
| --- | --- | --- | --- |
| `chatterbox` *(défaut du `.env.example`)* | Anglais uniquement | Lent sur CPU | Non |
| `kokoro` | `en`, `fr` | Local, ~5× temps réel sur CPU | 8 voix cataloguées |
| `moss` | Toutes | Local, lourd — GPU conseillé | Oui, banque de voix |
| `moss-remote` | Toutes | Déporté sur [`apps/tts-server`](apps/tts-server/README.md) | Oui, banque de voix |
| `openai` | Selon le serveur | Réseau, rapide, facturé | Voix du serveur |

- Démarrage en EN/FR sans GPU → `kokoro`.
- Autre langue → `moss`, `moss-remote` ou `openai`; `quality_profile=draft` ne
  convient pas, car il force Kokoro.
- Machine GPU séparée → `moss-remote`.

Une erreur TTS fait échouer le job explicitement : aucun fallback de voix
silencieux.

## Choisir son mode de production

| Choix | Utiliser quand | Point d'attention |
| --- | --- | --- |
| `quality_profile=draft` | Boucle rapide EN/FR | Force Kokoro et un rendu réduit. |
| `quality_profile=standard` | Livraison normale | Utilise la voix et le rendu configurés sur le serveur. |
| `quality_profile=high` | Livraison avec contrôle renforcé | Nécessite un modèle vision pour la revue visuelle complète. |
| `production_mode=technical` | Schémas, code, mathématiques, systèmes | Mode historique et prévisible. |
| `production_mode=editorial` | Explication sourcée et plus narrative | Demande un fournisseur de recherche si la recherche est requise. |
| `production_mode=cinematic` | Motion design Remotion à 60 fps | Plus coûteux en rendu et incompatible avec Manim. |
| `render_engine=manim` | Diagrammes techniques, graphes, équations | Pipeline Python historique. |
| `render_engine=remotion` | Compositions React et motion design | Utilise Node et Chrome headless dans le worker. |

La plateforme est actuellement optimisée pour les sujets STEM. Son architecture
est extensible, mais un nouveau domaine demande d'adapter les contrats
éditoriaux et les composants visuels, pas uniquement le prompt.

## Architecture

```text
studio (nginx) ou client HTTP
  -> FastAPI api
       -> Postgres (jobs et états)
       -> Redis (file Celery)
            -> worker
                 -> LLM / recherche / médias
                 -> TTS
                 -> Manim ou Remotion
                 -> ffmpeg et contrôles qualité
                 -> /data/jobs/<job_id>/
```

- `api` répond rapidement et ne rend jamais la vidéo lui-même.
- `worker` exécute les étapes longues et persiste chaque transition.
- `studio` sert le front-end et reverse-proxy `/v1` vers `api` : même origine,
  donc pas de CORS et lecture vidéo directe.
- `/data/jobs` est un volume Docker partagé; l'API n'écrit pas dans les exemples
  suivis par Git.
- `tts-server` est optionnel et permet de garder MOSS-TTS chargé sur une machine
  GPU dédiée.

## Organisation du dépôt

```text
.
├── compose.yaml                 # point d'entrée de la plateforme
├── Makefile                     # commandes d'onboarding et de développement
├── apps/
│   ├── video-api/               # produit principal
│   ├── studio/                  # interface web de pilotage
│   └── tts-server/              # service GPU optionnel
├── docs/                        # parcours, architecture et références
└── videos/
    ├── examples/                # MP4 de démonstration
    └── linux-fondamentaux/      # origine historique du projet
```

Voir [Organisation du dépôt](docs/REPOSITORY_STRUCTURE.md) pour les frontières
entre composants.

## Commandes utiles

```bash
make help       # liste les commandes
make doctor     # vérifie Docker et la configuration
make start      # build et démarrage en arrière-plan
make health     # vérifie l'API, Postgres et Redis
make status     # affiche les services
make logs       # suit api + worker
make down       # arrête sans supprimer les données
make test       # tests video-api; peut construire l'image si elle manque
make test-tts   # tests du service TTS optionnel
```

Ne lance pas `docker compose down -v` sauf si tu veux supprimer les jobs et la
base locale.

## Documentation

- [Commencer ici](docs/START_HERE.md)
- [Créer sa première vidéo](docs/FIRST_VIDEO.md)
- [Index de documentation](docs/README.md)
- [Studio, l'interface web](apps/studio/README.md)
- [Référence API](apps/video-api/docs/api-reference.md)
- [Architecture détaillée](apps/video-api/docs/architecture.md)
- [Guide développeur](apps/video-api/docs/developer-guide.md)
- [Exploitation et configuration](apps/video-api/docs/operations.md)
- [Contrat LLM](apps/video-api/docs/llm-contract.md)
- [Moteur Remotion](apps/video-api/docs/remotion-engine.md)
- [Production avancée](apps/video-api/docs/advanced-production.md)

## Sécurité avant exposition publique

Par défaut, l'API locale est ouverte. Avant de l'exposer sur un réseau, configure
`VIDEO_API_KEYS`, protège les secrets LLM/TTS, limite l'accès au volume des jobs
et configure `VIDEO_API_WEBHOOK_SECRET` si tu utilises les callbacks.

## Origine du projet

PromptLoom est né de deux vidéos Manim sur le kernel Linux et les appels système.
Ces productions ont imposé les principes qui structurent encore la plateforme :
la narration et l'image doivent raconter la même chose, les durées viennent de
l'audio réel et chaque livraison doit être vérifiée. Elles restent disponibles
dans `videos/linux-fondamentaux/` comme références historiques.

## Validation des contributions

Effectue les modifications d'abord, puis lance une seule passe de validation :

```bash
python3 -m py_compile $(find apps/video-api/src apps/video-api/tests -name '*.py' -print)
docker compose config --quiet
docker compose run --rm test
git diff --check
git status --short
```
