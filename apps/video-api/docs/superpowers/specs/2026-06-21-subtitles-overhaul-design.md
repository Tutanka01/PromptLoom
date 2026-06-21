# Refonte des sous-titres video-api

Date : 2026-06-21
Statut : approuvé, en implémentation

## Problème

Les sous-titres incrustés sont produits par `NarrationCaptions.tsx` à partir de
`alignment.json`, qui stocke la **forme normalisée pour l'alignement CTC**
(`pipeline/align.py::normalize_words`). Conséquences visibles :

1. **Texte affiché = forme normalisée** : minuscules, sans ponctuation, chiffres
   épelés (« 64-bit » → « sixty four bit », « ext4 » → « ext four »).
2. **Découpage mécanique** en blocs de 4 mots par index
   (`Math.floor(active/4)*4`) : coupe au milieu des syntagmes, saute tous les 4 mots.
3. **Multilingue cassé** : `normalize_words` ne garde que `[a-zA-Z']`, donc en
   français « été » → « t », « système » → « systme ». L'alignement (et donc les
   cues `beats`) est déjà dégradé hors anglais.
4. **Aucun fichier sous-titre standard** (`.srt` / `.vtt`).

## Décisions structurantes

- **Source de vérité unique en Python.** Le découpage en cues est calculé une
  fois (`pipeline/captions.py`). L'incrustation Remotion et l'export SRT/VTT
  consomment les mêmes cues → aucune dérive possible. `NarrationCaptions` devient
  un rendu « bête ».
- **Séparer le jeu de caractères d'alignement (perdant, CTC) du texte affiché
  (réel).** C'est la cause racine. On introduit une correspondance mot de surface
  → sous-tokens normalisés.
- **Multilingue par pliage de diacritiques (NFKD)** pour l'alignement uniquement
  (« été » s'aligne via « ete », s'affiche « été »). Scripts non-latins
  (arabe, cyrillique…) = limite documentée avec point d'extension (uroman).
- **Sidecar `.srt`/`.vtt`** (pas de re-mux d'une piste soft dans le MP4 canonique).

## Architecture

### 1. `pipeline/align.py` — mapping surface ↔ tokens
- `normalize_words(text)` (liste à plat normalisée) reste pour l'aligneur MMS_FA
  et `beats.py`, mais passe au pliage NFKD des diacritiques (au lieu de supprimer
  les caractères accentués).
- Nouvelle tokenisation de surface : pour chaque mot réel, ses sous-tokens
  normalisés (`"64-bit"` → surface `"64-bit"`, sous-tokens `["sixty","four","bit"]` ;
  `"kernel,"` → `["kernel"]` ; `"L'espace"` → `["l","espace"]`).
- Après alignement, timing du mot de surface = (début du 1er sous-token, fin du
  dernier). `alignment.json` gagne une clé `captions` (mots de surface + timing) ;
  `words` (normalisé) reste **inchangé** pour `beats.py`.

### 2. `pipeline/captions.py` (nouveau) — cœur qualité subtitle
- `build_cues(tokens)` — fonction pure, testable isolément :
  - coupe en priorité sur ponctuation forte (`. ! ? : ; …`),
  - budget ~42 car./ligne, max 2 lignes (~84 car./cue),
  - durée bornée (min ~0,8 s, max ~6 s), retour à la ligne au plus proche espace,
  - `cue.start/end` dérivés du timing audio.
- `write_subtitles(video_dir, slug, language)` :
  - lit `scenes_map.json` (fps + ordre), `alignment.json` (`captions`), `durations.json`,
  - construit les cues par scène (relatif scène) → **injecte `captionCues` dans
    `scenes_map.json` props** (en miroir de `beats._inject_cues`, en préservant `cues`),
  - applique l'offset cumulé `durations.json` (timeline audio = ce qui est parlé)
    → écrit `final/<slug>-<lang>.srt` et `.vtt` (timeline globale).

### 3. Remotion
- `build_video_json.py` : les props (dont `captionCues`) transitent déjà ;
  on **retire** l'injection `alignedWords` (désormais inutile).
- `NarrationCaptions.tsx` réécrit : consomme `captionCues` (cue active à l'instant
  t, 1–2 lignes, surlignage karaoké du mot courant, fondus). Modes conservés :
  `off`, `full`, `keywords` (cue affichée seulement près d'un cue visuel `cues`).

### 4. Pipeline & exposition
- `production.py` : appel `write_subtitles(...)` juste après `resolve_cues`,
  non-fatal (comme l'alignement).
- Les `.srt`/`.vtt` sont téléchargeables via l'endpoint artifacts existant
  (`/v1/videos/{id}/artifacts/...`) ; leurs chemins sont ajoutés au rapport.

## Hors périmètre (YAGNI)
- Pas de piste sous-titre soft re-muxée dans le MP4.
- Pas de romanisation non-latine.
- Pas d'éditeur de styles configurable.

## Addendum (2026-06-21) — piste continue unique

Premier rendu reel : sous-titres non homogenes (presents par moments, absents
plusieurs phrases). Cause racine confirmee sur le job (`video.json` :
`captionMode: "keywords"`, 8/8 scenes avec cues) : le mode `keywords` masquait
chaque cue hors d'une fenetre ±0,085 autour d'un beat, et le rendu se faisait
**dans** `SceneFrame` (donc fondu a chaque transition de scene).

Correctif (conforme a l'intuition « sous-titres a part, poses par-dessus ») :
- `captions.py` n'injecte plus `captionCues` par scene ; il ecrit une **liste
  globale** unique (`subtitles.json`, timeline video entiere, timings des mots
  inclus pour le karaoke).
- `build_video_json` expose `subtitles` au niveau racine de `video.json`.
- `NarrationCaptions.tsx` -> `SubtitleTrack` : monte **une seule fois** au niveau
  composition (hors `SceneFrame`), rendu continu, sans gating beats.
- Defaut avance bascule `keywords` -> `full` ; `keywords` rend desormais en
  continu (conserve par compatibilite).

Verifie par rendu local : sous-titre present en milieu de scene ET maintenu aux
frontieres de scenes (1,5 s et 3,0 s, a travers l'overlay de coupe).

## Tests
- `build_cues` : longueur de ligne, coupe ponctuation, durées min/max, 2 lignes.
- Mapping surface↔tokens : `64-bit`, ponctuation, apostrophe, diacritiques.
- SRT/VTT : offsets globaux cumulés, format horodatage, parité avec les cues
  incrustées.
- Garde-fou multilingue : un cas français (« été », accents préservés à l'affichage).
- Mise à jour `test_remotion_engine` (suppression assertion `alignedWords`).
