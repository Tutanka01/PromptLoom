# Operations

## Services Docker

L'application est definie dans `compose.yaml`.

Services :

- `api`: FastAPI sur le port `8080`.
- `worker`: Celery worker.
- `redis`: broker.
- `postgres`: metadonnees.
- `test`: service profile pour lancer `pytest`.

## Commandes utiles

Build :

```bash
docker compose build
```

Lancer toute l'application :

```bash
docker compose up
```

Lancer en arriere-plan :

```bash
docker compose up -d
```

Voir les services :

```bash
docker compose ps
```

Logs API :

```bash
docker compose logs -f api
```

Logs worker :

```bash
docker compose logs -f worker
```

Les logs du worker sont volontairement verbeux. Ils montrent :

- `worker.task.received`: un job est pris par Celery.
- `job.state`: transition de statut et progression.
- `job.attempt.start`: debut d'une tentative de production.
- `llm.request.start` / `llm.request.done`: appel au modele.
- `materialize.start` / `materialize.done`: ecriture des sources.
- `command.start` / `command.done`: commande externe lancee, duree, et fichier de log complet.
- `verify.*`: controles `ffprobe`, `freezedetect`, snapshots.
- `job.completed`: MP4 final pret.
- `job.attempt.failed` / `job.failed`: erreur et chemin du rapport.

Pour augmenter ou reduire le niveau de logs :

```text
VIDEO_API_LOG_LEVEL=INFO
VIDEO_API_LOG_LEVEL=DEBUG
```

Arreter :

```bash
docker compose down
```

Arreter et supprimer les volumes :

```bash
docker compose down -v
```

## Variables d'environnement

### LLM

```text
OPENAI_BASE_URL=http://your-server/v1
OPENAI_API_KEY=...
OPENAI_MODEL=...
VIDEO_API_LLM_TEMPERATURE=0.35
VIDEO_API_LLM_TIMEOUT_SECONDS=180
VIDEO_API_LLM_RESPONSE_FORMAT=none
```

`VIDEO_API_LLM_RESPONSE_FORMAT=json_object` peut etre active si ton endpoint supporte le mode JSON OpenAI-compatible.

### Mode fake

```text
VIDEO_API_FAKE_LLM=1
```

Utile pour tester l'application sans modele.

### Jobs et infrastructure

```text
VIDEO_API_LOG_LEVEL=INFO
VIDEO_API_DATABASE_URL=postgresql+psycopg://video:video@postgres:5432/video_api
VIDEO_API_REDIS_URL=redis://redis:6379/0
VIDEO_API_JOBS_ROOT=/data/jobs
VIDEO_API_REPO_ROOT=/workspace
VIDEO_API_MAX_REPAIR_ATTEMPTS=2
VIDEO_API_WORKER_CONCURRENCY=1
```

### Voix

```text
VIDEO_API_VOICE_ENGINE=chatterbox
VIDEO_API_VOICE_COMMAND=python generate_voice_en.py --engine chatterbox --exaggeration 0.45 --cfg-weight 0.55 --temperature 0.55 --tail-padding 0.45
```

Par defaut Docker utilise Chatterbox principal non-turbo. Pour utiliser un modele de
synthese vocale expose par le meme endpoint OpenAI-compatible que le LLM :

```text
VIDEO_API_VOICE_ENGINE=openai
VIDEO_API_OPENAI_TTS_MODEL=<modele-tts-expose-par-ton-serveur>
VIDEO_API_OPENAI_TTS_VOICE=<voix-supportee>
VIDEO_API_OPENAI_TTS_FORMAT=wav
VIDEO_API_OPENAI_TTS_SPEED=1.0
VIDEO_API_VOICE_TAIL_PADDING=0.45
```

Le worker reutilise `OPENAI_BASE_URL` et `OPENAI_API_KEY`. La cle est transmise en
variable d'environnement au script de voix, pas dans la commande loggee. Pour revenir
a Chatterbox, remettre `VIDEO_API_VOICE_ENGINE=chatterbox`.

Voix locale rapide (Kokoro, ~5x temps reel CPU vs Chatterbox, EN + FR) :

```text
VIDEO_API_VOICE_ENGINE=kokoro
VIDEO_API_VOICE_LANGUAGE=en        # en (lang_code "a") | fr (lang_code "f")
VIDEO_API_KOKORO_VOICE=af_bella    # voix Kokoro ; FR p.ex. ff_siwis
```

Kokoro et ses deps (`kokoro`, `misaki[en,fr]`) sont dans l'image worker ; le paquet
systeme `espeak-ng` (G2P, requis surtout pour le francais) est dans le `Dockerfile`.

### Manim

```text
MANIM_USE_UV=0
```

Dans Docker, Manim est deja installe dans l'image. `MANIM_USE_UV=0` evite de relancer `uv run --with manim` pendant les jobs.

### Moteur de rendu

```text
VIDEO_API_RENDER_ENGINE=manim     # manim (defaut) | remotion
VIDEO_API_REMOTION_DIR=           # optionnel, defaut <repo>/apps/video-api/remotion
```

Leviers vitesse du rendu **Remotion** (VM sans GPU, rendu CPU-bound ; toutes les passes
en profitent, sans effet sur Manim) :

```text
VIDEO_API_RENDER_FPS=30           # 30 (defaut) ~= 2x moins de frames qu'en 60
VIDEO_API_REMOTION_CONCURRENCY=75%  # entier ou %, "75%" ~= 12 tabs/16 coeurs ; "50%" si OOM
VIDEO_API_RENDER_X264_PRESET=faster # encode plus vite, qualite ~identique a crf 18
```

`verify.py` controle desormais `VIDEO_API_RENDER_FPS` (et plus 60 en dur) au pass final
pour le moteur Remotion ; Manim reste verifie a 60 fps (preset `-qh` fixe).

`remotion` bascule le rendu vers React/Remotion (palette de composants testes + code
libre encadre par scene), en gardant TTS Chatterbox, `assemble_en.sh` et `verify.py`.
L'image Docker embarque deja Node 20 + Chrome headless. Detail complet :
[Remotion Engine](remotion-engine.md). Rappel : chaque service compose a sa propre
image, donc apres un edit du `Dockerfile` rebuild explicitement (`docker compose ...
build worker api test`).

## Volumes

```text
video_jobs
postgres_data
```

`video_jobs` contient :

```text
/data/jobs/<job_id>/
  blueprint.json
  docs/
  videos/
  logs/
  reports/
```

`postgres_data` contient la base locale.

## Trouver les artefacts d'un job

Depuis un conteneur :

```bash
docker compose exec api ls -la /data/jobs
```

Pour inspecter un job :

```bash
docker compose exec api find /data/jobs/<job_id> -maxdepth 4 -type f
```

## Tests

```bash
docker compose run --rm test
```

Ce test ne lance pas un rendu complet. Il verifie la logique Python rapide.

Pour un smoke test HTTP :

```bash
docker compose up -d redis postgres api
curl http://localhost:8080/healthz
docker compose down
```

## GPU

Une base `compose.gpu.yaml` existe :

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up
```

Elle reserve des devices NVIDIA pour le worker.

Sur Apple Silicon, cette config GPU n'est pas utile. Chatterbox utilisera ce que Torch detecte dans le conteneur.

## Depannage

### L'API ne repond pas

Verifier :

```bash
docker compose ps
docker compose logs api
```

Si Postgres n'est pas healthy, l'API attendra ou echouera au demarrage.

### Un job reste en `queued`

Verifier que le worker tourne :

```bash
docker compose ps worker
docker compose logs worker
```

Si seul `api` est lance, les jobs peuvent etre crees mais ne seront pas executes.

### Erreur LLM

Verifier :

```text
OPENAI_BASE_URL
OPENAI_API_KEY
OPENAI_MODEL
```

Pour isoler le probleme :

```text
VIDEO_API_FAKE_LLM=1
```

### Erreur pendant Chatterbox

Consulter :

```text
/data/jobs/<job_id>/logs/voice.log
```

Ca peut venir :

- d'un modele non telechargeable ;
- d'un manque de RAM ;
- d'un probleme Torch ;
- d'une absence d'acces reseau si le modele doit etre recupere.

### Erreur Manim

Consulter :

```text
/data/jobs/<job_id>/logs/render-low.log
/data/jobs/<job_id>/logs/render-final.log
```

Verifier aussi les fichiers generes :

```text
/data/jobs/<job_id>/videos/<theme>/<slug>/<slug>_en.py
```

### Erreur qualite

Consulter :

```text
/data/jobs/<job_id>/reports/
```

Le job peut finir en `failed_quality` si `ffprobe` (pistes manquantes, resolution/fps,
duree sous le minimum) ou les snapshots echouent. Ces controles techniques restent bloquants.

Le `freezedetect`, lui, est par defaut un **avertissement, pas un echec** : une formule maths
tenue immobile compte comme "gelee", donc on prefere livrer le MP4 et laisser l'utilisateur
juger. Le detail va dans `report.json` -> `quality_warnings` et dans `reports/<low|final>/freeze.json`
(nombre, total, plus long gel + timestamp). Pour rebloquer le job sur un gel excessif, mettre
`VIDEO_API_FREEZE_FATAL=1`. Le seuil utilise deux signaux : total gele >
`max(VIDEO_API_FREEZE_FLOOR_SECONDS, duree * VIDEO_API_MAX_FREEZE_RATIO)` OU un seul gel >
`VIDEO_API_MAX_FREEZE_SINGLE_SECONDS`. Pour des videos legitimement statiques, augmente
`VIDEO_API_MAX_FREEZE_RATIO` et/ou `VIDEO_API_MAX_FREEZE_SINGLE_SECONDS`. Un gel unique tres
long reste le signal d'une scene reellement morte (a refaire).

## Notes de performance

L'image Docker actuelle est lourde parce que le worker embarque :

- Manim ;
- ffmpeg ;
- TeX minimal ;
- Chatterbox ;
- Torch ;
- dependances audio.

Pour accelerer les boucles de tests futures, une evolution utile serait de separer :

- image `api-test` legere ;
- image `worker-render` lourde.

Pour la v1, une seule image garde le deploiement plus simple.
