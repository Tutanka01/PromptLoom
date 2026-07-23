# Architecture

## Objectif

L'application transforme une requete courte en job video asynchrone.

Une requete HTTP ne doit pas attendre plusieurs minutes ou plusieurs heures pendant Chatterbox, Manim et ffmpeg. L'API cree donc un job, le met en queue, puis un worker l'execute et met a jour son etat.

## Services

```text
client
  |
  v
FastAPI api
  |
  +--> Postgres: metadonnees de jobs
  |
  +--> Redis: queue Celery
          |
          v
      Celery worker
          |
          +--> Tavily ou Exa (recherche optionnelle)
          +--> Pexels (acquisition optionnelle, avant rendu)
          +--> endpoint LLM compatible OpenAI
          +--> fichiers de production dans /data/jobs
          +--> Chatterbox
          +--> Manim ou Remotion
          +--> ffmpeg / ffprobe / freezedetect
```

## Composants

### `api`

Role :

- valider les requetes HTTP ;
- creer les jobs ;
- exposer les statuts ;
- exposer le rapport de verification ;
- servir le MP4 final.

Le service `api` ne rend pas la video. Il reste leger et rapide.

### `worker`

Role :

- appeler le LLM ;
- constituer un dossier de recherche source ;
- valider le blueprint ;
- resoudre les medias et leur provenance ;
- appliquer le gate de mouvement ;
- materialiser les fichiers de production ;
- generer la voix ;
- lancer Manim ou Remotion ;
- assembler avec ffmpeg ;
- verifier la video ;
- tenter une auto-reparation si une etape echoue.

Le worker est lourd. Il contient Manim, ffmpeg, Chatterbox, Torch et les dependances audio/video.

### `redis`

Redis sert de broker Celery. Il stocke les messages de jobs a executer.

### `postgres`

Postgres stocke les metadonnees :

- `job_id` ;
- prompt ;
- statut ;
- progression ;
- etape courante ;
- message d'erreur ;
- chemin du MP4 final ;
- chemin du rapport.

### Volume `video_jobs`

Le volume Docker partage `/data/jobs` entre `api` et `worker`.

Le worker ecrit les artefacts. L'API lit le MP4 final et les rapports pour les servir au client.

## Cycle de vie d'un job

Etats principaux :

```text
queued
researching
planning
asset_acquisition
motion_preflight
generating_sources
static_validation
voice_generation
audio_alignment
repairing
render_final
assemble_final
visual_review
verify_final
completed
failed_generation
failed_render
failed_quality
failed_visual_review
```

Le worker fait avancer le job et persiste chaque transition dans Postgres.

## Pipeline detaille

### 1. Creation du job

`POST /v1/videos` cree :

- une ligne `video_jobs` dans Postgres ;
- un dossier d'artefacts `data/jobs/<job_id>` dans le volume Docker ;
- un message Celery dans Redis.

### 2. Generation LLM

Quand la requete active la recherche, le worker constitue d'abord
`research.json` via Tavily ou Exa. Le LLM recoit uniquement des extraits bornes
avec des identifiants stables. Le worker demande ensuite un `VideoBlueprint` a
un endpoint compatible OpenAI.

Le blueprint contient :

- titre ;
- theme ;
- slug ;
- duree cible ;
- domaine academique et niveau ;
- audience ;
- objectif pedagogique ;
- objectifs d'apprentissage ;
- style visuel ;
- scenes ;
- duree et primitive visuelle par scene ;
- narration par scene ;
- beats visuels par scene.
- references `source_ids` par scene.

Les options resolues (`technical`, `editorial`, `cinematic`) sont persistees
dans `video_jobs.production_config`. Un retry ou une video secondaire de batch
rejoue donc exactement le meme contrat. Les secondaires reutilisent la
recherche et le blueprint maitre de la primaire.

### 3. Validation

Le blueprint est valide avec Pydantic.

Les regles importantes :

- cles de scenes au format `Scene1_HookEN` ;
- scenes ordonnees ;
- beats ordonnes ;
- dernier beat utile vers la fin de la scene ;
- textes assez longs pour produire une narration utile.

### 4. Materialisation

Le worker cree une structure proche du pipeline manuel :

```text
data/jobs/<job_id>/
  docs/videos/<theme>/<slug>/
    plan.md
    script.md
  videos/<theme>/<slug>/
    segments_en.json
    beats_en.json
    <slug>_en.py
    <slug>_style.py
    generate_voice_en.py
    render_en.sh
    assemble_en.sh
```

Pour un job avance, le workspace contient aussi :

```text
research.json
proposal.json
scene_plan.json
asset_manifest.json
motion_plan_report.json
```

Les medias Remotion sont telecharges avant le rendu depuis un provider
allow-list, controles, hashes, puis servis depuis le dossier local du job. Une
acquisition impossible devient une scene diagrammatique deterministe.

Avant la materialisation, le gate anti-diaporama mesure la couverture de
mouvement, la repetition, la densite textuelle, les beats et les sources. En
mode avance, son echec declenche une reparation puis bloque le job si necessaire.
Les plans cinematiques varies et totalement synchronises peuvent continuer sans
media quand aucun visuel reel n'est semantiquement justifie ; ce cas est trace
comme avertissement et reste soumis au gate `freezedetect` apres rendu.

Le code Manim est ensuite ecrit par scene par l'etape `scene_coder` (LLM guide par
`manim-skill.md`), qui produit du vrai Manim (LaTeX, axes, code, diagrammes). Chaque scene
passe la securite AST, le contrat de synchro, le check des noms indefinis, un smoke render
(une frame de la scene isolee) et `py_compile` ; une scene qui echoue toutes ses tentatives
retombe sur un template deterministe — c'est ce qui garantit que le render global ne meurt
pas sur une scene fautive. Pour forcer le mode 100% deterministe : `VIDEO_API_SCENE_CODER_ENABLED=0`.

### 5. Voix

Le worker lance `generate_voice_en.py`.

Par defaut :

```text
Chatterbox principal non-turbo
```

Le moteur de voix est configurable avec `VIDEO_API_VOICE_ENGINE` :

- `chatterbox` : lance la commande locale `VIDEO_API_VOICE_COMMAND` ;
- `kokoro` : TTS local rapide (~5x temps reel CPU), EN + FR, pilote par
  `VIDEO_API_VOICE_LANGUAGE` (en/fr) et `VIDEO_API_KOKORO_VOICE` ;
- `moss` : MOSS-TTS Hugging Face/local, multilingue, pilote par la langue du job
  API et `VIDEO_API_MOSS_TTS_MODEL`. Par defaut, si aucune reference audio
  explicite n'est fournie, le premier segment genere/reutilise devient la
  reference de voix pour les segments suivants ;
- `openai` : appelle le endpoint OpenAI-compatible `OPENAI_BASE_URL` via `/audio/speech`.

Le resultat attendu :

```text
audio/en/<scene>.wav
audio/en/<scene>.padded.wav
audio/en/durations.json
audio/en/voiceover_en.wav
```

Le chemin audio reste en PCM de bout en bout : chaque WAV de segment est paddé,
puis les WAV paddés sont concaténés sans encodage avec perte dans
`voiceover_en.wav`. `durations.json` pilote la synchronisation Manim ou Remotion.
L'assemblage applique le mastering et le loudnorm au WAV global, puis encode
directement l'unique piste AAC du MP4 final. Il n'existe plus de MP3
intermédiaire, ni par segment ni pour la voix globale.

### 6. Rendu final

Le worker rend directement en qualite finale (il n'y a plus de rendu basse
qualite : la revue visuelle inspecte desormais le fichier exact qui est livre) :

```bash
QUALITY=qh ./render_en.sh
./assemble_en.sh
```

La video finale doit etre en 1080p60 avec audio. Un job qui passe est rendu
exactement une fois ; une revue visuelle en echec coute un rendu complet
supplementaire (par choix : les scenes fautives sont reecrites puis re-rendues).

### 7. Revue visuelle (optionnelle)

Activee par `VIDEO_API_VISION_ENABLED=1`. Elle s'execute apres l'assemblage final
et avant la verification, sur le MP4 final assemble (le fichier qui sera livre) :

1. Extrait trois frames par scene (debut / milieu / fin, via `audio/en/durations.json`).
2. Envoie toutes les frames + le contexte narration/beats a un modele vision (`VIDEO_API_VISION_MODEL`).
3. Le modele note chaque scene sur 5 dimensions (poids entre parentheses) :
   - `narration_match` (0.35) : l'image correspond a ce qui est dit.
   - `readability` (0.20) : texte lisible, non coupe.
   - `framing` (0.20) : rien hors cadre, pas de chevauchement.
   - `density` (0.15) : une idee active a la fois.
   - `not_blank` (0.10) : ecran non vide.
4. Le worker calcule le score pondere 0-100 et applique la regle blocker :
   - `passed = score >= VIDEO_API_VISION_MIN_SCORE (defaut 75) ET aucun defaut "blocker"`.
5. Si `passed=False`, le job repart en reparation avec un `repair_hint` listant les problemes par scene
   (reparation au niveau scene : seules les scenes fautives sont reecrites, puis re-rendues).
   Apres epuisement des tentatives : `failed_visual_review`.
6. Si `passed=True`, le job passe a la verification.

Variables d'environnement :

```text
VIDEO_API_VISION_ENABLED=1
VIDEO_API_VISION_MODEL=<nom-du-modele-vision>   # meme endpoint que OPENAI_BASE_URL
VIDEO_API_VISION_MIN_SCORE=75
VIDEO_API_VISION_MAX_TOKENS=1500
```

Les frames de revue sont ecrites sous `reports/review/vision/`, le rapport dans
`reports/visual_review.json`, et le resultat est attache sous la cle
`visual_review` dans `report.json` final.

### 8. Verification

Le worker execute :

- `ffprobe` pour confirmer les streams, durees, resolution, fps ;
- `freezedetect` pour detecter les longues parties statiques ;
- extraction de snapshots une par une.

Si les controles echouent, le job passe dans une boucle d'auto-reparation.

### 9. Auto-reparation

Le worker peut relancer un prompt de reparation avec :

- blueprint precedent ;
- erreur ;
- etape echouee ;
- logs disponibles.

Par defaut, `VIDEO_API_MAX_REPAIR_ATTEMPTS=2`.

Si les tentatives echouent, le job finit en erreur explicite. L'API ne renvoie pas une video douteuse comme si elle etait valide.

## Isolation des artefacts

Les jobs API ne sont pas ecrits dans le dossier racine `videos/` du depot.

Ils sont ecrits dans :

```text
/data/jobs/<job_id>
```

Dans Docker Compose, ce chemin correspond au volume :

```text
video_jobs
```

Cette separation evite de polluer les sources manuelles du projet.

## Concurrence

Le worker est configure avec une concurrence de 1 par defaut :

```text
VIDEO_API_WORKER_CONCURRENCY=1
```

Raison :

- Chatterbox peut saturer CPU/GPU/RAM ;
- Manim et ffmpeg sont lourds ;
- plusieurs rendus simultanes peuvent ralentir tout le serveur et rendre les erreurs plus difficiles a diagnostiquer.

Pour scaler, la bonne evolution est d'ajouter plusieurs workers controles, idealement avec ressources isolees.
