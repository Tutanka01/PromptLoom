# Developer Guide

Ce guide explique comment travailler sur `apps/video-api`.

## Structure du code

```text
apps/video-api/
  compose.yaml
  Dockerfile
  pyproject.toml
  src/video_api/
    main.py
    tasks.py
    celery_app.py
    config.py
    db.py
    models.py
    schemas.py
    storage.py
    pipeline/
      llm.py
      materialize.py
      validate.py
      commands.py
      verify.py
      production.py
  tests/
  docs/
```

## Responsabilites par module

### `main.py`

Application FastAPI :

- demarrage DB ;
- `POST /v1/videos` ;
- status ;
- download ;
- report.

### `tasks.py`

Point d'entree Celery :

- initialise la DB cote worker ;
- lance `VideoPipeline`.

### `schemas.py`

Schemas Pydantic :

- requetes/reponses HTTP ;
- contrat du blueprint LLM ;
- validation des scenes et beats.

Ce fichier est une barriere importante contre les sorties LLM invalides.

### `pipeline/llm.py`

Client LLM compatible OpenAI.

Il supporte :

- endpoint configurable par `OPENAI_BASE_URL` ;
- modele configurable par `OPENAI_MODEL` ;
- mode fake via `VIDEO_API_FAKE_LLM=1` ;
- extraction JSON ;
- reparation de blueprint invalide.

### `pipeline/materialize.py`

Transforme un `VideoBlueprint` valide en fichiers de production.

Il ecrit :

- `plan.md` ;
- `script.md` ;
- `segments_en.json` ;
- `beats_en.json` ;
- code Manim ;
- style ;
- scripts `render_en.sh` et `assemble_en.sh`.

Important : le code Manim est genere depuis un template deterministe. Le LLM ne fournit pas directement du Python arbitraire.

### `pipeline/validate.py`

Validation statique :

- presence de `segments_en.json` ;
- presence de `beats_en.json` ;
- coherence `key` / `class` ;
- parsing AST des fichiers Python ;
- `py_compile`.

### `pipeline/commands.py`

Wrapper pour les commandes externes.

Il capture stdout/stderr et ecrit les logs dans :

```text
data/jobs/<job_id>/logs/
```

### `pipeline/verify.py`

Verification video :

- `ffprobe` ;
- `freezedetect` ;
- extraction de snapshots.

### `pipeline/production.py`

Orchestrateur principal.

Il gere :

- transitions d'etat ;
- tentatives de reparation ;
- ecriture des rapports ;
- statut final.

## Ajouter une nouvelle etape au pipeline

1. Ajouter la fonction dans `pipeline/`.
2. L'appeler depuis `VideoPipeline._run_with_repairs`.
3. Mettre a jour les statuts/progressions.
4. Ecrire les logs dans le dossier du job.
5. Ajouter au moins un test si l'etape contient de la logique propre.
6. Mettre a jour [architecture.md](architecture.md) si le cycle de vie change.

## Modifier le contrat LLM

1. Modifier les modeles Pydantic dans `schemas.py`.
2. Modifier le prompt et le schema attendu dans `pipeline/llm.py`.
3. Adapter `pipeline/materialize.py`.
4. Ajouter un test avec `fake_blueprint`.
5. Tester avec Docker :

```bash
docker compose run --rm test
```

## Modifier la generation Manim

La v1 genere des scenes simples a partir de templates.

Le point principal est `_scene_code()` dans `pipeline/materialize.py`.

Regles :

- garder `begin_sync()`, `play_until()`, `finish_sync()` ;
- ne pas ajouter de `wait()` arbitraire ;
- limiter la densite visuelle ;
- garder des labels courts ;
- eviter de faire executer du Python brut retourne par le LLM.

## Tests

Les tests doivent etre lances avec Docker :

```bash
cd apps/video-api
docker compose run --rm test
```

Depuis la racine du depot :

```bash
docker compose -f apps/video-api/compose.yaml run --rm test
```

Validation Compose :

```bash
docker compose -f apps/video-api/compose.yaml config --quiet
```

Build complet :

```bash
docker compose -f apps/video-api/compose.yaml build
```

## Smoke test API

```bash
docker compose up -d redis postgres api
curl http://localhost:8080/healthz
curl -X POST http://localhost:8080/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Make a short video explaining derivatives intuitively","theme":"math"}'
docker compose down
```

## Rendu complet

Pour tester un vrai rendu, il faut lancer aussi le worker :

```bash
docker compose up --build
```

Puis creer un job.

Attention : un rendu complet peut etre long et consommer beaucoup de CPU/GPU/RAM.

## Bonnes pratiques

- Ne pas ecrire les jobs API dans le dossier source `videos/`.
- Ne pas supprimer les volumes avec `docker compose down -v` sans vouloir perdre les jobs.
- Garder le worker a concurrence 1 tant que Chatterbox/Manim ne sont pas profiles.
- Ajouter les validations avant d'ajouter de l'automatisation LLM plus libre.
- Ne pas servir un MP4 si les controles finaux echouent.
