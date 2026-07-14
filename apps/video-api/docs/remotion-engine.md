# Moteur de rendu Remotion (video-api)

Moteur de rendu alternatif à Manim, activé par `VIDEO_API_RENDER_ENGINE=remotion`.
Une requête API → un blueprint LLM → TTS Chatterbox → rendu Remotion → assemble
ffmpeg → vérif → MP4. **Manim reste le défaut** ; bascule par variable d'env, zéro
régression sur l'existant.

## Principe : même couture que Manim

Le pipeline shell-out sur des scripts d'un `video_dir`. Le moteur Remotion écrit le
**même contrat** que Manim ; seul `render_en.sh` change. Voice / assemble / verify /
visual_review sont partagés (`pipeline/engine.py` sélectionne le moteur, le reste de
`production.py` est commun).

```
video_dir/
  segments_en.json      # {segments:[{key,title,text}]}  -> generate_voice_en.py (Chatterbox)
  generate_voice_en.py  # copié à l'identique -> audio/en/durations.json + voiceover_en.mp3
  scenes_map.json       # {fps, scenes:[{key, component, custom, props}]} (ordonné)
  build_video_json.py   # durations.json + scenes_map.json -> video.json
  render_en.sh          # build video.json, injecte l'entrée par job, npx remotion render -> final/<slug>-en-silent.mp4
  assemble_en.sh        # partagé avec Manim : mux silent + voiceover -> final/<slug>-en-final.mp4
  remotion_scenes/*.tsx # composants Custom générés (scene-coder)
  jobScenes_index.ts    # re-exporte les Custom -> COMPONENTS
```

`durationInFrames` par scène = `round(durations[key] * render_fps)` (fps configurable,
défaut **30** via `VIDEO_API_RENDER_FPS`). Le rendu est **silencieux**
(`embedAudio:false`) ; `assemble_en.sh` muxe la voix off globale.

## Blueprint (contrat LLM)

`schemas.RemotionBlueprint` / `RemotionScene`. Champs miroir de Manim (key ordonnée
`Scene1_…EN`, `title`, `narration`, `duration_seconds`) + `component` + `props` +
`visual_intent` + `source_ids`. Les gates de durée/narration sont partagées avec Manim via
`video_api.timing` : un blueprint qui valide ici a assez de narration pour passer
`verify_mp4`. Prompt + normalisation : `pipeline/remotion_blueprint.py`
(`expr → points` échantillonnés en sandbox, clamp des ranges, alias de champs).

### Palette de composants testés (`remotion/src/scenes/data/scenes.tsx`)

| Composant            | Props clés |
|----------------------|------------|
| `TitleScene`         | `title, subtitle?, accent?` |
| `BulletScene`        | `title, bullets[2-5], caption?, accent?` |
| `FormulaScene`       | `title, formulas[1-3] (LaTeX/KaTeX), caption?` |
| `CodeScene`          | `title, code, lang, codeTitle?, caption?` |
| `PlotScene`          | `title, expr|points|curves[{expr\|points,label,dash?,color?}], markers?[{x,y,label?,guides?}], xRange, yRange? (omit → auto-fit), sweep?, area?, xLabel?, yLabel?` |
| `DiagramScene`       | `title, nodes[{id,label,x(-6..6),y(-3..3),color?}], edges[{from,to,label?}]` |
| `ComparisonScene`    | `title, left{label,items[2-5]}, right{label,items[2-5]}, caption?` |
| `LayeredSystemScene` | `title, layers[{label,sub?,color?}][2-5], caption?` |
| `TimelineScene`      | `title, steps[{label,sub?}][2-5], caption?` |
| `TerminalScene`      | `title, command, output?, caption?` |
| `MemoryScene`        | `title, cells[{label?,sub?,color?,highlight?}][≤12], cols?(1-6), caption?` |
| `FlowScene`          | `title, stages[{label,sub?}][2-5], caption?` (paquet qui traverse) |
| `BarChartScene`      | `title, bars[{label,value,color?}][2-6], caption?` |
| `CounterScene`       | `title, value, prefix?, suffix?, label?, decimals?, caption?` |
| `QuoteScene`         | `quote, author?, accent?` (citation plein écran mot-à-mot) |
| `SplitFocusScene`    | `title?, left{kind,…}, right{kind,…}, caption?` ; kinds: `code\|plot\|formula\|bullets\|terminal` |
| `ZoomNarrativeScene` | `canvas[{id,label,x(-6..6),y(-3..3),sub?,detail?}], path?, accent?` (caméra zoom/pan) |
| `NetworkMapScene`    | `nodes[{id,label,group?}], links[{a,b,label?}]` (positions auto-calculées en Python) |
| `ImageScene`         | `title, asset_query` puis `src` local, `motion?, credit?` |
| `FootageScene`       | `title, asset_query` puis `src` local, `mediaDurationSeconds, credit?` |

Transitions inter-scènes : le fond `AmbientBackground` reste persistant et des
overlays de coupe (`minimal`, `editorial`, `cinematic`) sont poses a la frontiere
des sequences. Les scenes ne se chevauchent pas : la voix muxee sequentiellement
reste exactement synchro. Les sous-titres sont une **piste unique continue**
(`SubtitleTrack`) posee au niveau composition, au-dessus de toutes les scenes,
donc elle ne fond jamais avec les transitions et ne depend pas des beats.
`pipeline/captions.py` regroupe les mots alignes en cues globales (1-2 lignes
equilibrees, coupees sur la ponctuation, duree bornee) affichant le **vrai texte**
(casse, ponctuation, accents, chiffres reels) avec surlignage karaoke ; il ecrit
la liste dans `subtitles.json` (lue par le rendu) et le meme contenu en sidecar
`final/<slug>-<lang>.srt` + `.vtt`, donc incruste et fichier ne peuvent pas
diverger. `captionMode` vaut `off` (masque) ou `full`/`keywords` (continu). Les
transitions de scene sont purement visuelles : aucun effet sonore n'est ajoute
aux coupes.

### Direction artistique (thèmes bornés)

Le blueprint choisit une palette via le champ `art_direction` (un de `default`,
`blueprint`, `forest`, `synthwave`, `carbon`, `plum` — defini dans `THEMES` de
`remotion/src/style/tokens.ts`, miroir Python `REMOTION_THEMES`, parite testee).
`default` reproduit exactement l'ancien look dark-academic ; un thème invalide est
ramene a `default` (`normalize_remotion_blueprint`). Le LLM en choisit un selon le
sujet/ton ; c'est une palette par video, complementaire de `accent` (toujours par
scene).

Mecanique : `colors.*` sont des variables CSS (`var(--c-x, <defaut>)`) ; la racine
`MainComposition` pose les `--c-*` du thème actif via `applyThemeVars(theme)`. Les
~112 usages `colors.x` restent inchanges. **Regles d'authoring** (palette comme
Custom) : pour la translucidite utiliser `alpha(color, 0.2)` (depuis `../../lib`,
base `color-mix`) — jamais `${color}33` (invalide sur une variable CSS) ; en SVG
appliquer les couleurs via `style={{ stroke, fill }}`, pas via les attributs
`stroke=`/`fill=` (les variables CSS n'y resolvent pas).

### Escape hatch `Custom` (code libre encadré)

Quand aucune palette ne convient, le blueprint met `component:"Custom"` + un
`visual_intent`. `pipeline/remotion_scene_coder.py` fait écrire au LLM un composant
TSX autonome (`export const Scene3_…EN: React.FC<any> = ({dur, ...props}) => …`),
puis l'**encadre** (analogues des gardes Manim) :

1. allow-list d'imports : seulement `react`, `remotion`, et le barrel `../../lib` ;
2. scan d'API interdites (`eval`/`Function`/`fetch`/`require`/`import()`/`process`/`fs`/…) ;
3. export du nom exact = clé de scène ;
4. `tsc --noEmit` sur le projet avec le candidat en place ;
5. smoke `remotion still` d'une frame de la scène isolée.

Échec après `VIDEO_API_SCENE_CODER_ATTEMPTS` tentatives → **fallback déterministe**
vers une `BulletScene` construite depuis la narration (`fallback_custom_to_palette`).
Le rendu global réussit toujours. Désactiver le code libre :
`VIDEO_API_SCENE_CODER_ENABLED=0` (toutes les scènes Custom retombent sur la palette).

Surface autorisée pour le code libre : le barrel `remotion/src/lib.ts` (catalogue +
primitives + style + hooks Remotion courants). Skill LLM : `docs/remotion-skill.md`.

## Isolation par job

`render_en.sh` injecte les scènes Custom + une **entrée par job** dans le projet
Remotion partagé sous un id unique : `src/jobScenes/<id>/` et `src/entries/<id>.tsx`
(nettoyés via `trap` en fin de rendu). Pas de mutation de fichiers partagés → sûr en
concurrence ; `node_modules` résolus depuis le projet partagé. `$VIDEO_API_REMOTION_DIR`
override le chemin (défaut `repo_root/apps/video-api/remotion`).

## Qualité / verify

`verify_mp4` ne vérifie 1920×1080 + `render_fps` (défaut 30) et le gate de freeze qu'au
**pass final** (`final_quality=True`). Donc `QUALITY=ql` rend en `--scale=0.5` (preview
rapide) et `QUALITY=qh` en `--scale=1 --crf=18`. GL : `swangle` (logiciel, sûr en headless
Docker).

**Leviers vitesse (VM sans GPU, rendu CPU-bound)** — toutes les passes en profitent :
`--concurrency=$VIDEO_API_REMOTION_CONCURRENCY` (défaut `"75%"` ≈ 12 tabs/16 cœurs ;
~0,5–1 Go/tab → baisser à `"50%"` si OOM), `--x264-preset=$VIDEO_API_RENDER_X264_PRESET`
(défaut `faster`), et `VIDEO_API_RENDER_FPS` (défaut 30, ~2× moins de frames que 60).

## Docker

Le `Dockerfile` ajoute Node 20, les libs de Chrome headless, `npm ci` du projet
Remotion et `npx remotion browser ensure` (Chrome Headless Shell pré-téléchargé).
Image partagée api/worker/test → le flag marche sans rebuild.

## Activation

```bash
# .env a la racine ou environnement Compose
VIDEO_API_RENDER_ENGINE=remotion
# (optionnel) forcer 100% palette, sans code libre
VIDEO_API_SCENE_CODER_ENABLED=0
```

```bash
docker compose -f apps/video-api/compose.yaml up -d
curl -X POST localhost:8080/jobs -H 'content-type: application/json' \
  -d '{"prompt":"Explain virtual memory and page tables","theme":"cs"}'
```
