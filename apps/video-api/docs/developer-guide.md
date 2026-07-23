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
      research.py
      assets.py
      editorial.py
      materialize.py
      remotion_materialize.py
      remotion_scene_coder.py
      align.py
      beats.py
      captions.py
      voice.py
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
- reparation de blueprint invalide ;
- contexte de production et dossier de recherche bornes.

### `pipeline/research.py`

Adapters Tavily/Exa. Cette etape produit des sources normalisees et stables ;
elle ne laisse jamais le LLM choisir une URL ou un endpoint.

### `pipeline/assets.py`

Resout les `asset_query` Remotion via Pexels, telecharge les medias dans le
workspace, valide domaine/type/taille, calcule leur hash et produit un fallback
deterministe en cas d'echec.

### `pipeline/editorial.py`

Ecrit `proposal.json` et `scene_plan.json`, puis applique les gates de promesse
editoriale avant et apres rendu.

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

Le blueprint reste du JSON valide. Le code par scene est produit par un scene
coder encadre (Manim ou TSX Remotion), avec validation et fallback
deterministe ; le LLM ne peut pas injecter de code arbitraire non controle.

### `pipeline/voice.py`

Gère la signature du moteur vocal et le cache audio par segment. Les
matérialiseurs appellent `prune_stale_audio` : seuls les WAV dont le texte ou le
profil vocal a changé sont supprimés, puis régénérés. Les WAV inchangés restent
réutilisables lors d'une réparation.

Le script `generate_voice_en.py` matérialisé conserve ensuite une chaîne PCM
directe :

```text
<scene>.wav -> <scene>.padded.wav -> voiceover_en.wav
             -> mastering/loudnorm -> AAC du MP4 final
```

Il ne doit produire aucun MP3 intermédiaire. En mode `moss-remote`, un segment
prêt est téléchargé dans `<scene>.wav.part`, validé comme WAV PCM16 mono 24 kHz
complet, puis publié avec `os.replace`. Un échec ne doit ni remplacer un WAV
valide existant ni laisser de fichier `.part`.

### `pipeline/align.py`

Alignement force mot a mot (Remotion). Apres le TTS, `align_segments` projette
chaque WAV sur sa narration (torchaudio MMS_FA) et ecrit `audio/en/alignment.json` :

- `words` : tokens normalises pour l'aligneur CTC et le matching de beats ;
- `captions` : les **vrais mots de surface** (casse, ponctuation, accents,
  chiffres reels) avec leur timing, via `surface_tokens` (correspondance mot reel
  -> sous-tokens d'alignement) + pliage NFKD des diacritiques cote alignement
  seulement (multilingue latin).

Per-segment non fatal, cache par empreinte de voix (reutilise les timings
inchanges).

### `pipeline/beats.py`

Resout les `beats[].anchor` du blueprint contre les `words` alignes en
`props.cues` (ratios de progression de scene), pour reveler chaque item visuel
quand il est prononce. Cues forcees croissantes ; anchor non trouve => timing par
defaut pour cet item.

### `pipeline/captions.py`

Source de verite unique des sous-titres (opt-in via `captions`). `build_cues`
(fonction pure) regroupe les `captions` alignees en cues lisibles (coupe sur la
ponctuation, 1-2 lignes equilibrees <= ~42 car., duree bornee). `write_subtitles`
decale chaque scene sur la timeline globale (somme cumulee de `durations.json`,
la voix etant un flux continu) et ecrit `subtitles.json` (piste continue lue par
Remotion) + `final/<slug>-<langue>.srt`/`.vtt`. Incruste et sidecar partagent les
memes cues, donc ne peuvent pas diverger.

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
- configuration de production persistee par job ;
- recherche, assets et motion preflight ;
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
docker compose run --rm test
```

Pour cibler explicitement le fichier du composant :

```bash
docker compose -f apps/video-api/compose.yaml run --rm test
```

Validation Compose :

```bash
docker compose config --quiet
```

Build complet :

```bash
docker compose build
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
