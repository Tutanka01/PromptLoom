# Procedure operationnelle v2 pour produire une video

Ce projet sert a produire des videos explicatives haut de gamme sur Linux avec Manim, une voix off locale, puis un assemblage audio/video synchronise.

La methode actuelle n'est plus seulement "une duree audio par scene". Le standard v2 ajoute une synchro par beats narratifs : l'audio fixe toujours la duree totale, mais l'image avance a des points precis de la narration.

Documents a lire avant de modifier ou creer une video :

```text
AGENTS.md
docs/VIDEO_PRODUCTION_STANDARD.md
docs/boilerplate/README.md
```

Videos de reference :

```text
videos/linux-fondamentaux/001-c-est-quoi-le-kernel/final/kernel-intro-en-final.mp4
videos/linux-fondamentaux/002-c-est-quoi-un-syscall/final/syscall-intro-en-final.mp4
```

La premiere montre le pipeline historique stable. La seconde est le premier exemple du standard v2 avec `beats_en.json`, helpers `play_until(...)`, et refonte visuelle pilote.

## Principe non negociable

La voix et l'image doivent raconter la meme chose au meme moment.

Si la narration parle de scheduler, l'image montre le scheduler. Si elle parle de privilege CPU, l'image montre user mode, kernel mode, frontiere, entree controlee et retour. Si la scene affiche seulement une illustration generique pendant que la voix explique un mecanisme precis, la scene doit etre repensee.

## Structure attendue par video

Chaque video a deux emplacements.

Documentation narrative :

```text
docs/videos/<thematique>/<numero-slug>/
  plan.md                   # intention, public, arc narratif, scenes, style
  script.md                 # narration humaine
```

Fichiers de production :

```text
videos/<thematique>/<numero-slug>/
  segments_en.json          # source de verite pour le TTS
  beats_en.json             # beats narratifs et visuels, standard v2
  <slug>_en.py              # scenes Manim synchronisees
  <slug>_style.py           # design system local
  generate_voice_en.py      # generation TTS locale
  render_en.sh              # rendu Manim + video silencieuse
  assemble_en.sh            # mux audio/video
  audio/en/                 # genere : WAV/MP3/durations.json
  final/                    # MP4 final et silent MP4
  renders/                  # snapshots et controles visuels
```

Adapter les noms Python au sujet. Garder le principe : la documentation dans `docs/videos/...`, les fichiers executables et donnees de production dans `videos/...`.

Ne pas ajouter de README, notes de voix ou documentation operationnelle dans les dossiers video. La documentation reusable vit dans `docs/`. Les dossiers video gardent seulement les sources necessaires a la production.

Pour creer une nouvelle video, partir du boilerplate :

```text
docs/boilerplate/
```

## Ordre de travail obligatoire

1. Comprendre le sujet, le public vise et le niveau de prerequis.
2. Mettre a jour `docs/videos/<thematique>/<numero-slug>/plan.md` avec l'arc narratif, les scenes, le design et les risques.
3. Ecrire `docs/videos/<thematique>/<numero-slug>/script.md` avec une narration naturelle, une section par scene.
4. Creer ou mettre a jour `segments_en.json`.
5. Creer ou mettre a jour `beats_en.json` pour piloter les moments visuels importants.
6. Verifier que chaque scene a une intention visuelle concrete.
7. Generer ou reutiliser la voix locale Chatterbox.
8. Produire `audio/en/durations.json`.
9. Implementer les scenes Manim avec `begin_sync()`, `play_until(...)`, `hold_until(...)`, `finish_sync()`.
10. Rendre en basse qualite.
11. Assembler l'audio et la video basse qualite.
12. Mesurer `ffprobe`, `freezedetect`, puis inspecter les snapshots.
13. Corriger le script, le timing ou le visuel si necessaire.
14. Rendre en 1080p60.
15. Assembler le MP4 final.
16. Refaire `ffprobe`, `freezedetect`, snapshots, puis `git status --short`.
17. Donner le chemin du MP4 final et les limites restantes si tout n'est pas parfait.

Ne pas sauter les verifications. Une video non verifiee n'est pas terminee.

## Plan et narration

`docs/videos/<thematique>/<numero-slug>/plan.md` doit au minimum contenir :

- sujet ;
- audience ;
- objectif pedagogique ;
- idee cle ;
- arc narratif ;
- liste des scenes ;
- intention visuelle de chaque scene ;
- regles de couleur et typographie ;
- risques connus ;
- criteres d'acceptation.

`docs/videos/<thematique>/<numero-slug>/script.md` doit contenir la voix off humaine. Une scene doit etre assez courte pour rester visuellement controlable. Si une scene couvre trop de concepts, la couper en plusieurs scenes ou renforcer ses beats.

## Segments TTS

`segments_en.json` est la source de verite pour la voix.

Schema attendu :

```json
{
  "segments": [
    {
      "key": "Scene1_HookEN",
      "class": "Scene1_HookEN",
      "title": "A command is not direct",
      "text": "Voiceover text for this exact scene."
    }
  ]
}
```

Regles :

- l'ordre des segments est l'ordre narratif final ;
- `key`, `class`, et `scene_key` doivent correspondre ;
- ne pas changer un texte deja accepte sans raison ;
- si un texte change, regenerer seulement l'audio necessaire quand le script le permet.

## Beats narratifs

Le fichier `beats_en.json` decrit les moments importants a l'interieur d'une scene. Il ne remplace pas `durations.json`; il sert a placer les actions visuelles dans la duree audio.

Schema attendu :

```json
{
  "Scene1_HookEN": [
    {
      "key": "command",
      "at": 0.08,
      "text_hint": "The phrase heard around this moment.",
      "visual_action": "The visual action that should happen now."
    }
  ]
}
```

Regles :

- `at` est un ratio entre `0.0` et `1.0` de la duree audio de la scene ;
- viser 5 a 7 beats par scene importante ;
- placer le dernier changement visuel utile vers 0.80 a 0.90 ;
- chaque beat doit relier une phrase entendue a une action visuelle precise ;
- eviter les beats vagues comme "show something" ou "make it nice" ;
- si une scene reste figee pendant que la voix continue, ajouter un beat ou repenser la scene.

## Voix locale

Mode prefere :

```text
Chatterbox principal non-turbo
```

Commande type :

```bash
uv run --python 3.11 --with chatterbox-tts python generate_voice_en.py \
  --engine chatterbox \
  --exaggeration 0.45 \
  --cfg-weight 0.55 \
  --temperature 0.55 \
  --tail-padding 0.45
```

Regles :

- ne pas utiliser `say` macOS pour une version finale ;
- ne pas remplacer Chatterbox principal par Turbo sans demander ;
- ne pas regenerer une voix deja acceptee sans raison ;
- laisser `generate_voice_en.py` reutiliser les WAV existants si possible ;
- verifier que `audio/en/durations.json` est produit ;
- verifier que `audio/en/voiceover_en.mp3` existe.

Verification rapide :

```bash
cat audio/en/durations.json
ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 audio/en/voiceover_en.mp3
```

La somme de `durations.json` doit etre proche de la duree du voiceover global.

## Synchronisation Manim v2

Chaque scene doit rester pilotee par la duree audio reelle.

Pattern attendu :

```python
class SceneX_NameEN(EnglishVideoScene):
    scene_key = "SceneX_NameEN"
    fallback_duration = 35

    def construct(self):
        self.begin_sync()

        self.play_until(0.08, FadeIn(title))
        self.play_until(0.25, FadeIn(first_visual))
        self.play_until(0.52, Transform(...))
        self.hold_until(0.72)
        self.play_until(0.88, FadeIn(summary))

        self.finish_sync()
        self.play(FadeOut(...), run_time=0.7)
```

La classe de base doit fournir :

- `begin_sync()` : enregistre le depart et ajoute les sous-titres si disponibles ;
- `scene_duration()` : lit `audio/en/durations.json`, avec fallback ;
- `cue(ratio)` : convertit un ratio de scene en temps absolu Manim ;
- `play_until(ratio, *animations)` : joue une animation jusqu'au beat vise ;
- `hold_until(ratio)` : attend jusqu'au beat vise sans casser la duree ;
- `finish_sync(trailing_animation=0.7)` : attend seulement le temps restant avant fade-out.

Regles :

- ne pas ajouter des `wait()` arbitraires ;
- ne pas resoudre une scene trop courte par un long ecran statique final ;
- faire evoluer l'image jusqu'a au moins 80-90% de la scene ;
- utiliser `FadeIn` pour les labels qui doivent rester propres a tous les timestamps ;
- utiliser `Write` seulement si l'effet lettre par lettre est intentionnel et accepte visuellement.

## Design system Manim

Chaque video doit avoir un fichier style local, par exemple :

```text
syscall_style.py
kernel_style.py
```

Il doit contenir :

- couleurs nommees ;
- tailles typographiques ;
- fond commun ;
- cartes et boites stables ;
- helpers de connexion ;
- helpers d'attention : `focus`, `dim`, `undim`, `glow` ;
- helpers de mouvement : `flow_dot` ou equivalent.

Regles visuelles :

- typography lisible, labels courts, plancher autour de 18 px ;
- titres moins enormes que l'espace utile de la scene ;
- un element actif a la fois ;
- contexte attenue quand il n'est pas le sujet ;
- environ 7 elements importants visibles au maximum ;
- revelation progressive ;
- boites aux dimensions fixes pour eviter les deplacements ;
- contours neutres au repos, accent seulement sur l'element actif ;
- pas de `Circumscribe()` repete comme mecanique principale d'attention ;
- pas de texte coupe, hors cadre ou serre dans une boite.

## Rendu basse qualite

Depuis le dossier video :

```bash
QUALITY=ql ./render_en.sh
./assemble_en.sh
```

Verifier la video basse qualite avant de passer au final :

```bash
ffprobe -v error -show_entries format=duration,size -show_streams -of json final/<video>-final.mp4
ffmpeg -i final/<video>-final.mp4 -vf freezedetect=n=-60dB:d=3 -an -f null -
```

Pour un resume compact de `freezedetect` :

```bash
ffmpeg -i final/<video>-final.mp4 -vf freezedetect=n=-60dB:d=3 -an -f null - 2>&1 \
  | awk '/freeze_duration/ {count += 1; total += $NF} END {printf "freezes=%d total=%.2f avg=%.2f\n", count, total, (count ? total/count : 0)}'
```

Objectifs :

- pilotes : aucun freeze non intentionnel > 4 s ;
- video complete : total de freeze fortement reduit par rapport a la baseline ;
- a 30%, 60%, 90% d'une scene pilote, l'image doit avoir change et accompagner la voix.

## Snapshots

Toujours extraire les frames une par une :

```bash
mkdir -p renders/final_checks
ffmpeg -y -ss 00:00:10 -i final/<video>-final.mp4 -frames:v 1 -update 1 renders/final_checks/check_0010.png
ffmpeg -y -ss 00:01:30 -i final/<video>-final.mp4 -frames:v 1 -update 1 renders/final_checks/check_0130.png
ffmpeg -y -ss 00:03:00 -i final/<video>-final.mp4 -frames:v 1 -update 1 renders/final_checks/check_0300.png
```

Inspecter :

- texte coupe ;
- labels hors cadre ;
- mots partiellement dessines par `Write` ;
- chevauchements incoherents ;
- ecran vide ou trop sparse ;
- fleches qui traversent du texte ;
- focus visuel ambigu ;
- mismatch entre narration et image.

Ne pas utiliser une commande multi-input avec plusieurs `-ss`; elle peut sortir plusieurs fois la meme frame.

## Rendu final

Quand la basse qualite est propre :

```bash
QUALITY=qh ./render_en.sh
./assemble_en.sh
```

Verifier :

```bash
ffprobe -v error -show_entries format=duration,size -show_streams -of json final/<video>-final.mp4
```

Attendu :

- stream video present ;
- stream audio present ;
- 1920x1080 ;
- 60 fps ;
- video H.264 ;
- audio AAC mono ;
- duree audio et video quasiment identiques ;
- pas de video anormalement courte ou muette.

Refaire `freezedetect` et les snapshots apres le rendu final. Les controles basse qualite ne suffisent pas.

## Pieges connus

### MP3 concatenes avec `-c copy`

Eviter de concatener directement des MP3 encodes separement. Cela peut produire des timestamps non monotones et une duree globale fausse.

Solution : creer des WAV paddes par scene, concatener les WAV, puis encoder une seule fois le voiceover final.

### Padding video sans padding audio

Si Manim attend entre les scenes mais que l'audio global n'a pas le meme silence, la video se decale progressivement.

Solution : le generateur de voix doit ajouter le meme padding dans les fichiers audio paddes et dans `durations.json`.

### Fade-out ajoute apres la duree cible

Si `finish_sync()` attend jusqu'a la duree audio puis qu'on ajoute un fade-out, chaque scene devient trop longue.

Solution : `finish_sync(trailing_animation=0.7)` retire le temps du fade-out final.

### Animation de texte fragile

`Write(Text(...))` peut afficher un mot partiellement dessine sur un snapshot intermediaire.

Solution : utiliser `FadeIn` pour les labels fonctionnels, garder `Write` pour les titres ou effets intentionnels.

### Scene statique mais audio long

Un `hold` de 8 a 15 secondes peut techniquement synchroniser, mais donne une impression de video figee.

Solution : ajouter des beats, de la focalisation, un token de flux, une transformation ou une revelation progressive.

## Definition de termine

Une video est terminee seulement si :

- `docs/videos/<thematique>/<numero-slug>/plan.md` existe ;
- `docs/videos/<thematique>/<numero-slug>/script.md` ou `script_en.md` existe ;
- `segments_en.json` existe ;
- `beats_en.json` existe pour les scenes v2 ou pilotes ;
- les scenes Manim existent ;
- le design system local existe ;
- les segments audio et `durations.json` existent ;
- le voiceover global existe ;
- la video silencieuse existe ;
- le MP4 final audio+video existe ;
- `ffprobe` confirme audio et video ;
- `freezedetect` a ete mesure ;
- plusieurs snapshots ont ete inspectes ;
- `git status --short` a ete consulte ;
- le chemin final est donne a l'utilisateur.

Si une condition manque, le dire explicitement au lieu de presenter la video comme terminee.
