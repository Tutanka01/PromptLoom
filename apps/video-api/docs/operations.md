# Operations

## Services Docker

La plateforme est lancee depuis le `compose.yaml` de la racine. Celui-ci inclut
les definitions de services maintenues dans `apps/video-api/compose.yaml`.

Services :

- `api`: FastAPI sur le port `8080`.
- `worker`: Celery worker.
- `redis`: broker.
- `postgres`: metadonnees.
- `test`: service profile pour lancer `pytest`.

## Commandes utiles

Les commandes suivantes sont a lancer depuis la racine du depot.

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

Par defaut Docker utilise Chatterbox principal non-turbo. Le champ API `language`
choisit la langue de sortie demandee au LLM et transmise au TTS. Pour les langues
au-dela de EN/FR, utiliser `VIDEO_API_VOICE_ENGINE=moss` et eviter
`quality_profile=draft`, car `draft` force Kokoro pour accelerer les iterations.

Pour utiliser un modele de
synthese vocale multilingue MOSS-TTS :

```text
VIDEO_API_VOICE_ENGINE=moss
VIDEO_API_MOSS_TTS_MODEL=OpenMOSS-Team/MOSS-TTS-v1.5
VIDEO_API_MOSS_TTS_DEVICE=auto       # auto | cpu | cuda | mps
VIDEO_API_MOSS_TTS_DTYPE=auto        # auto garde bf16 sur CPU/CUDA pour limiter la RAM
VIDEO_API_MOSS_TTS_VOICE=            # optionnel si le modele expose des voix nommees
VIDEO_API_MOSS_TTS_REFERENCE_AUDIO=  # optionnel, zero-shot cloning si supporte
VIDEO_API_MOSS_TTS_REFERENCE_TEXT=   # texte de la reference, si requis
VIDEO_API_MOSS_TTS_CONSISTENT_VOICE=1 # stabilise automatiquement la voix entre scenes
VIDEO_API_VOICE_TAIL_PADDING=0.45
```

La langue parlee vient du champ API `language` du job. Les fichiers restent
nommes `segments_en.json` et `audio/en/...` pour compatibilite avec le pipeline
existant, mais leur contenu narratif peut etre francais, espagnol, italien,
roumain, anglais, etc. Avec `VIDEO_API_MOSS_TTS_CONSISTENT_VOICE=1`, si
`VIDEO_API_MOSS_TTS_REFERENCE_AUDIO` est vide, le premier WAV de scene sert de
reference pour les scenes suivantes afin d'eviter de passer d'une voix masculine
a une voix feminine entre deux scenes. Si ton installation MOSS utilise une commande specifique,
tu peux fournir une commande par segment :

```text
VIDEO_API_MOSS_TTS_COMMAND=python -m moss_tts --model {model} --language {language} --text-file {text_file} --output {output}
```

Placeholders disponibles : `{text_file}`, `{text_json}`, `{output}`, `{language}`,
`{model}`, `{reference_audio}`, `{reference_text}`. Pour beneficier de
`VIDEO_API_MOSS_TTS_CONSISTENT_VOICE=1` avec une commande externe, la commande
doit transmettre `{reference_audio}` au moteur TTS si celui-ci accepte une
reference de voix.

Pour deporter MOSS-TTS sur un serveur GPU dedie (voir `apps/tts-server/README.md`),
le moteur `moss-remote` envoie les textes des segments au serveur et telecharge
les WAV ; le modele reste charge en VRAM la-bas entre les jobs :

```text
VIDEO_API_VOICE_ENGINE=moss-remote
VIDEO_API_TTS_SERVER_URL=http://<ip-serveur-gpu>:8100
VIDEO_API_TTS_SERVER_API_KEY=<cle>
VIDEO_API_TTS_SERVER_TIMEOUT=3600
```

La voix coherente fonctionne comme en local : si une partie des WAV existe deja
(reparation), le premier WAV local est envoye comme reference de clonage pour que
le timbre ne change pas. Le serveur a aussi son propre cache par contenu : seuls
les segments modifies sont resynthetises. Si le serveur est injoignable ou si le
job TTS echoue, le job video echoue avec l'erreur dans `logs/voice.log` — il n'y
a pas de bascule silencieuse vers une autre voix.

Pour utiliser un modele de synthese vocale expose par le meme endpoint
OpenAI-compatible que le LLM :

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

### Production avancee : recherche et medias

Les modes `editorial` et `cinematic` sont choisis dans le JSON de
`POST /v1/videos`, pas avec une bascule globale. Ils exigent par defaut une
recherche disponible :

```text
VIDEO_API_RESEARCH_PROVIDER=tavily       # tavily | exa | none
VIDEO_API_RESEARCH_API_KEY=
VIDEO_API_RESEARCH_TIMEOUT_SECONDS=45
```

Les medias stock sont opt-in par requete (`visuals.allow_stock`) et par
configuration serveur :

```text
VIDEO_API_ASSET_PROVIDER=pexels          # pexels | none
VIDEO_API_PEXELS_API_KEY=
VIDEO_API_ASSET_MAX_DOWNLOAD_MB=80
```

Le worker telecharge avant le rendu et n'accepte que les domaines Pexels. En
cas d'echec, la scene devient un diagramme ; le job ne rend jamais une URL
distante. Pour un environnement sans provider, utiliser le mode `technical` ou
envoyer `research: {"enabled": false}` / `visuals: {"allow_stock": false}`.

Les artefacts de diagnostic sont `research.json`, `asset_manifest.json` et
`motion_plan_report.json`. Un echec de recherche requise ou de promesse de
mouvement finit en `failed_generation`. Un echec du delivery gate apres rendu
finit en `failed_quality`.

### Synchro narration <-> visuel + sous-titres (Remotion)

```text
VIDEO_API_ALIGN_ENABLED=1         # alignement force mot a mot (torchaudio MMS_FA)
VIDEO_API_ALIGN_DEVICE=auto       # auto | cpu | cuda
VIDEO_API_CAPTION_MODE=off        # defaut serveur : off | full | keywords
```

Apres le TTS, le worker aligne chaque WAV sur sa narration et resout les
`beats[].anchor` du blueprint en `props.cues` : chaque item visuel apparait
quand ses mots sont prononces. Non fatal : sans alignement, les scenes gardent
leurs timings par defaut. Le cache (`audio/en/cache.json`) evite de realigner
les segments inchanges.

Le **sous-titrage** est opt-in (champ `captions` de la requete ;
`VIDEO_API_CAPTION_MODE` n'est que le defaut serveur, surcharge par la requete et
par le mode de production). Quand `captions != off`, `pipeline/captions.py`
projette les timings d'alignement sur le vrai texte (casse, ponctuation, accents,
chiffres reels), regroupe en cues lisibles (1-2 lignes equilibrees) et ecrit :

- `subtitles.json` : la liste globale lue par Remotion et rendue comme **une
  seule piste continue** au-dessus de toute la video (jamais coupee par les
  scenes/transitions) ;
- `final/<slug>-<langue>.srt` + `.vtt` : sidecar (meme contenu) liste dans
  `report.subtitles`.

`captions: "off"` ne produit aucun sous-titre (ni incruste, ni fichier).
L'alignement, lui, tourne quand meme s'il est active (il pilote les `cues`).

### Generation LLM

```text
VIDEO_API_BLUEPRINT_TWO_PASS=1    # outline puis 1 appel par scene en parallele
VIDEO_API_BLUEPRINT_SCENE_ATTEMPTS=2  # retries cibles par scene invalide
VIDEO_API_LLM_PARALLEL=3          # appels LLM concurrents (scene coders + pass 2)
```

### Musique de fond (optionnelle)

```text
VIDEO_API_MUSIC_FILE=             # chemin d'un fichier audio visible du worker
VIDEO_API_MUSIC_DB=-26            # niveau de base ; ducking automatique sous la voix
```

### Loudness audio (normalisation EBU R128)

`assemble_en.sh` applique un etage `loudnorm` (single-pass) pour que chaque video
sorte au meme niveau percu, independamment du moteur TTS. Sans musique la voix est
normalisee ; avec musique c'est le mix final (voix + musique duckee) qui l'est.

```text
VIDEO_API_AUDIO_LOUDNORM_ENABLED=1   # 0 = mux brut sans normalisation (comportement historique)
VIDEO_API_AUDIO_LOUDNESS_TARGET=-14  # loudness integre cible en LUFS (-14 = norme YouTube/streaming)
VIDEO_API_AUDIO_TRUE_PEAK=-1.5       # plafond true-peak en dBTP
VIDEO_API_AUDIO_QC_FATAL=0           # 1 = un clipping / quasi-silence mesure fait echouer le job
```

Le QC audio mesure le rendu final (loudness integre + true peak), ecrit
`reports/final/audio_stats.json`, et signale (warning par defaut) un true peak > 0 dBTP
(clipping) ou un quasi-silence.

### API et exploitation

```text
VIDEO_API_KEYS=                   # cles API (separees par des virgules) ; vide = ouvert
VIDEO_API_WEBHOOK_SECRET=         # signe les webhooks callback_url (HMAC-SHA256)
VIDEO_API_TASK_TIME_LIMIT_SECONDS=10800  # plafond Celery par job (soft ; hard = +300s)
VIDEO_API_STALE_JOB_HOURS=6       # reaper au demarrage de l'API (jobs figes -> failed_stale)
VIDEO_API_JOB_TTL_DAYS=15         # retention : supprime /data/jobs/<id> des jobs terminaux > 15j ; 0 = jamais
VIDEO_API_GC_INTERVAL_HOURS=6     # cadence du GC periodique (Celery beat dans le worker)
```

### Retention des artefacts

Les workspaces de jobs (`/data/jobs/<job_id>/`) sont supprimes automatiquement
au-dela de `VIDEO_API_JOB_TTL_DAYS` (defaut 15 jours). Seuls les jobs terminaux
sont concernes (`completed`, `cancelled`, `failed*`) ; la ligne en base est
conservee pour l'historique, mais ses chemins d'artefacts sont remis a vide
(les endpoints `download` / `report` renvoient alors un 404 propre).

Le balayage tourne a deux endroits, de facon idempotente :

- au demarrage de l'API (immediat apres un deploiement / restart) ;
- periodiquement dans le worker via Celery beat (`video_api.gc_job_artifacts`,
  toutes les `VIDEO_API_GC_INTERVAL_HOURS`, defaut 6h), pour qu'un serveur qui
  ne redemarre jamais respecte quand meme la limite.

Mettre `VIDEO_API_JOB_TTL_DAYS=0` desactive completement la retention (les
artefacts sont gardes indefiniment).

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
docker compose -f compose.yaml -f apps/video-api/compose.gpu.yaml up
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
