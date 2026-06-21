# Design — Lot 1 : 4 nouveaux archétypes de scènes Remotion

Date : 2026-06-21
Statut : approuvé (design), en attente de revue du spec écrit
Branche : `feat/remotion-scene-archetypes`

## Contexte

Le moteur Remotion de `video-api` (`VIDEO_API_RENDER_ENGINE=remotion`) possède déjà
une palette data-driven de 16 composants que le blueprint LLM compose par
`{component, props}`, un escape hatch `Custom` encadré, des transitions
`SceneFrame`, des captions mot-à-mot (`NarrationCaptions` via alignement forcé) et
des cues narration-synchronisées (`props.cues`). Ce lot **étend la palette** avec
4 archétypes à fort impact visuel, **sans toucher** au reste du pipeline ni
introduire de dépendance ou coût externe.

Objectif : des scènes plus « cinématiques » tout en restant déterministes et en
réutilisant intégralement le plumbing existant (cues, captions, transitions,
fallback, vérif).

## Principes (imposés par l'existant — non négociables)

- Chemin **data-driven** uniquement (pas de `Custom`). Le blueprint choisit la
  scène par nom + props ; aucun code TSV n'est généré à l'exécution.
- Chaque composant consomme sa durée via le prop **`dur`** et pilote ses beats sur
  `p = useCurrentFrame() / dur`. Jamais `useVideoConfig().durationInFrames`.
- **Pas** de `@remotion/transitions` / `TransitionSeries` dans une scène (cela
  chevauche les voisines et désynchronise la voix off muxée séquentiellement).
- **Pas** de fade global de la scène par elle-même : `SceneFrame` possède
  l'enveloppe entrée/sortie. Chaque scène garde son dernier beat stabilisé avant
  `p ≈ 0.9`.
- Réveler les items via `cueOr(cues, i, défaut)` (depuis `style/anim`) : item `i`
  apparaît quand ses mots sont prononcés ; `null` retombe sur l'espacement par
  défaut. Jamais de temps absolu codé en dur.
- **Aucune frame cassée** : props requises manquantes/invalides → `degrade()` +
  repli déterministe sur `BulletScene` (via `_bullets_from_narration`).

## Points de contact (identiques pour les 4 scènes)

| Fichier | Modification |
|---|---|
| `src/video_api/schemas.py` | nom ajouté à `REMOTION_PALETTE` (tuple) **et** à `RemotionComponent` (Literal) |
| `src/video_api/pipeline/remotion_blueprint.py` | branche dans `_normalise_props` (clamps, défauts, `degrade()`), ligne `_PALETTE_LINE` (signature vue par le LLM), alias optionnels dans `_COMPONENT_ALIASES`, guidance « quand l'utiliser » |
| `remotion/src/scenes/data/scenes.tsx` | composant React, pattern `Shell` + `cueOr`/`dimAt`/`appear` |
| `remotion/src/registry.ts` | import + entrée dans `SCENE_COMPONENTS` |
| `docs/remotion-catalog.md` + `docs/remotion-engine.md` | tables de palette mises à jour |

Surface React autorisée : `react`, `remotion`, le barrel `../../lib` (catalogue +
primitives + `style/tokens` + `style/anim`). Réutiliser les primitives existantes
(`Card`, `Arrow`, `CodeBlock`, `Plot`, `MathFormula`, `Terminal`, `TextReveal`,
`TitleBar`, `Caption`) plutôt que réinventer.

## Les 4 archétypes

### 1. `QuoteScene`

- **But** : moment headline/émotionnel — grande citation centrée révélée mot-à-mot.
- **Props** : `{ quote: str, author?: str, accent?: "#hex" }`.
- **Rendu** : `quote` via `TextReveal` (mot-à-mot, grande taille, kerning soigné),
  trait/marque d'accent ; `author` apparaît au 2ᵉ cue. Pas de `Shell` titre
  obligatoire (scène pleine page), mais respecte l'enveloppe `SceneFrame`.
- **Cues** : 1 (citation) à 2 (citation, auteur).
- **Fallback** : `quote` absente → 1ʳᵉ phrase de la narration (tronquée proprement).
- **Clamps** : longueur `quote` ≤ ~240 car. (sinon réduction de taille de police).

### 2. `SplitFocusScene`

- **But** : deux panneaux vivants synchronisés (cause/effet, code + son effet).
  Distinct de `ComparisonScene` (2 listes statiques).
- **Props** : `{ title?: str, left: Panel, right: Panel, caption?: str }`
  où `Panel = { kind, ... }` et **`kind ∈ {code, plot, formula, bullets, terminal}`**.
  - `code`   : `{ kind, code, lang?, codeTitle? }`  → `CodeBlock`
  - `plot`   : `{ kind, expr|points, xRange?, yRange?, xLabel?, yLabel? }` → `Plot`
  - `formula`: `{ kind, formulas[1..2] }` → `MathFormula`
  - `bullets`: `{ kind, bullets[2..4], heading? }` → liste révélée
  - `terminal`: `{ kind, command, output? }` → `Terminal`
- **Rendu** : deux colonnes 50/50. Panneau gauche révélé sur `cues[0]`, droit sur
  `cues[1]`, puis stagger interne propre à chaque kind. `title`/`caption` via
  `Shell`.
- **Cues** : 2+ (gauche, droite, puis items internes).
- **Fallback** : un seul panneau valide ou kind inconnu → `BulletScene` construit
  depuis la narration.
- **Décision de portée (v1)** : `image`/`footage` **exclus** des kinds. Les
  inclure obligerait l'`AssetResolver` à descendre dans les props imbriquées
  (résolution + provenance + fallback par panneau) — surcoût non justifié pour le
  lot 1. Les 5 kinds retenus sont 100 % déterministes, sans asset externe.
  `image` ajoutable en lot 2.

### 3. `ZoomNarrativeScene`

- **But** : effet caméra cinématique (Prezi/semantique) — révélation progressive en
  se déplaçant/zoomant dans un grand canvas.
- **Props** : `{ canvas: [{id, label, x(-6..6), y(-3..3), sub?, detail?}], path?: [id...], accent? }`.
  - Coordonnées fournies par le LLM (comme `DiagramScene`), clampées au repère
    Manim-like (`mx/my/mu`, 1 unité = 135px, origine centrée, y-haut).
  - `path` = ordre de visite caméra ; défaut = ordre de `canvas`.
- **Rendu** : un « monde » `AbsoluteFill` interne transformé par
  `translate(...) scale(...)` interpolé sur des keyframes alignées aux cues. À
  chaque cue, la caméra centre+zoome sur `canvas[path[i]]` et révèle son `detail` ;
  au dernier beat, dézoom en vue d'ensemble. Items rendus en `Card`.
- **Cues** : `len(path)` (+1 pour la vue d'ensemble finale).
- **Fallback** : `< 2` items de canvas → `BulletScene`.
- **Clamps** : `canvas` ≤ 8 items ; `x/y` clampés ; `path` filtré aux `id` connus,
  dédupliqué, complété par les items non visités.

### 4. `NetworkMapScene`

- **But** : graphe/réseau animé pour systèmes complexes (plus grand que
  `DiagramScene`, dont les positions sont manuelles et le nombre de nœuds petit).
- **Props (entrée LLM)** : `{ nodes: [{id, label, group?}], links: [{a, b, label?}] }`.
  **Le LLM ne fournit PAS les positions.**
- **Layout déterministe (Python)** : `remotion_blueprint.py` calcule `nodes[].x/y`
  via un layout seedé (placement circulaire + relaxation légère ; seed dérivé de
  la clé de scène). Même seed → mêmes positions (déterminisme requis par le rendu).
  Positions clampées au repère.
- **Rendu** : nœuds = `Card`/`Pill` qui s'allument aux cues ; arêtes = `Arrow` avec
  `progress` 0→1 tracé après l'apparition des deux extrémités. Couleur par `group`.
- **Cues** : nombre de nœuds, **cap ≤ 10** (au-delà, items supplémentaires révélés
  à l'espacement par défaut).
- **Fallback** : `nodes` vide → `BulletScene`.
- **Clamps** : `nodes` ≤ 10, `links` ≤ 20, `links` filtrés aux `id` existants.

## Flux de données & cues

Inchangé, on s'y branche :

```
blueprint LLM (beats[].anchor, une phrase par item visible dans l'ordre d'affichage)
   → TTS → align.py (alignement mot-à-mot) → beats.py
   → props.cues: (number|null)[]  (un ratio par item)
   → composant React: cueOr(cues, i, défaut)
```

**Travail clé par scène** : définir et **documenter l'ordre des items** (donc des
beats attendus) dans la ligne `_PALETTE_LINE`, pour que le mapping beats→cues soit
correct. Exemples :
- `QuoteScene` : [citation, auteur].
- `SplitFocusScene` : [panneau gauche, panneau droit, puis items internes].
- `ZoomNarrativeScene` : ordre de `path`.
- `NetworkMapScene` : ordre de `nodes`.

## Gestion d'erreurs & fallbacks

- Chaque branche de `_normalise_props` valide les props requises ; à défaut,
  `degrade("<Scene> raison")` puis repli sur `BulletScene` (déterministe).
- Tous les nombres/longueurs de liste/coords sont clampés (`_clamp_range` et
  helpers).
- Côté React, props optionnelles tolérées (valeurs par défaut), aucune exception à
  l'exécution. Une scène ne doit jamais produire de frame noire/figée
  (freezedetect).

## Tests

- **Python** (`tests/`) : unitaires `_normalise_props` par scène —
  - props manquantes → fallback `BulletScene` + dégradation enregistrée ;
  - clamps (coords, longueurs, ranges) ;
  - `NetworkMapScene` : layout déterministe (même seed ⇒ mêmes positions) ;
  - parité `REMOTION_PALETTE` (schemas) ↔ `SCENE_COMPONENTS` (registry) ↔
    `_PALETTE_LINE`.
- **TS / Remotion** : `tsc --noEmit` du projet + smoke `remotion still` d'une frame
  par nouvelle scène (réutilise le harnais de smoke existant).
- **Validation finale (une passe)** : `py_compile` sur src+tests,
  `docker compose config -q`, `git diff --check`, `git status --short`, puis un
  **smoke render** Docker d'un job exerçant les 4 scènes, avec inspection
  ffprobe/freezedetect/snapshots.

## Hors périmètre (lot 1)

- Kind `image`/`footage` dans `SplitFocusScene` (lot 2 : nécessite l'`AssetResolver`).
- Visuels génératifs IA (nouveau provider d'assets) — chantier séparé.
- Direction artistique / thèmes — chantier séparé.
- Nouvelles transitions cinématiques — chantier séparé.

## Critères de succès

- Le blueprint LLM peut proposer les 4 scènes ; elles valident Pydantic et
  passent les gates de durée/narration partagés.
- Rendu déterministe, synchro audio préservée, captions/cues fonctionnels.
- Aucun chemin ne casse le rendu global (fallback systématique).
- Docs (`remotion-catalog.md`, `remotion-engine.md`) cohérentes avec le code.
