# Procedure pour la prochaine IA

Ce projet sert a produire des videos explicatives haut de gamme sur Linux avec Manim, une voix off locale, puis un assemblage audio/video synchronise.

La video de reference actuelle est :

```text
videos/linux-fondamentaux/001-c-est-quoi-le-kernel/final/kernel-intro-en-final.mp4
```

Elle est en anglais, dure environ 4 min 35, utilise Chatterbox principal non-turbo pour la voix, et synchronise les scenes Manim sur les durees reelles des segments audio.

## Structure attendue

Chaque video doit vivre dans un dossier dedie :

```text
videos/<thematique>/<numero-slug>/
  plan.md                  # intention, narration, scenes
  script.md                # script narratif humain
  segments_en.json         # texte par scene, source de verite pour la voix
  kernel_intro_en.py       # scenes Manim synchronisees
  generate_voice_en.py     # generation TTS locale
  render_en.sh             # rendu Manim + concat video silencieuse
  assemble_en.sh           # mux video + audio
  audio/en/                # WAV/MP3 par scene + voiceover final
  final/                   # fichiers finaux
```

Ne pas melanger les videos entre elles. Creer un nouveau dossier pour chaque sujet.

## Regles de qualite

1. Ne pas faire une video ou la voix raconte une chose pendant que l'image en montre une autre.
2. Decouper le script en scenes courtes, chacune avec un objectif visuel clair.
3. La duree de chaque scene doit venir de l'audio genere, pas d'une estimation manuelle.
4. Toujours verifier les snapshots de rendu : texte coupe, elements qui se chevauchent, scene vide.
5. Rendre d'abord en basse qualite, corriger, puis seulement ensuite en 1080p60.
6. Ne pas utiliser la voix macOS `say` pour une version finale. Elle est acceptee seulement pour prototypage rapide.

## Pipeline recommande

Depuis le dossier de la video :

```bash
cd videos/linux-fondamentaux/001-c-est-quoi-le-kernel
```

### 1. Ecrire ou mettre a jour les segments

Le fichier `segments_en.json` est la source de verite pour la voix. Chaque entree doit avoir :

```json
{
  "key": "Scene1_HookEN",
  "class": "Scene1_HookEN",
  "title": "What is the Linux kernel?",
  "text": "Voiceover text for this exact scene."
}
```

L'ordre dans `segments_en.json` doit etre le meme que l'ordre narratif final.

### 2. Generer la voix

Mode prefere : Chatterbox principal, non-turbo.

```bash
uv run --python 3.11 --with chatterbox-tts python generate_voice_en.py \
  --engine chatterbox \
  --exaggeration 0.45 \
  --cfg-weight 0.55 \
  --temperature 0.55 \
  --tail-padding 0.45
```

Notes importantes :

- Le modele principal peut etre lent sur Mac avec MPS. C'est normal.
- `generate_voice_en.py` reutilise les WAV existants si `--force` n'est pas passe.
- Utiliser `--force` seulement si on veut vraiment regenerer une voix existante.
- Le script cree `audio/en/durations.json`.
- Le script cree aussi `audio/en/voiceover_en.wav` puis `audio/en/voiceover_en.mp3`.
- Le silence de fin de scene doit exister dans l'audio global, pas seulement dans Manim.

Verification :

```bash
cat audio/en/durations.json
ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 audio/en/voiceover_en.mp3
```

La somme des valeurs de `durations.json` doit correspondre a la duree du voiceover.

### 3. Synchroniser les scenes Manim

Dans le script Manim, chaque scene doit :

```python
class SceneX_NameEN(EnglishKernelScene):
    scene_key = "SceneX_NameEN"

    def construct(self):
        self.begin_sync()
        # animations
        self.finish_sync()
        self.play(FadeOut(...), run_time=0.7)
```

Le helper `finish_sync()` soustrait le fade-out final pour que la duree totale de la scene reste alignee avec l'audio.

Ne pas ajouter un `self.wait()` arbitraire apres `finish_sync()` sans mettre a jour la logique de synchronisation.

### 4. Rendre en basse qualite

```bash
QUALITY=ql ./render_en.sh
```

Verifier la duree de la video silencieuse :

```bash
ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 final/kernel-intro-en-silent.mp4
```

Elle doit etre proche de la duree du voiceover, idealement a moins d'une seconde.

### 5. Rendre en qualite finale

```bash
QUALITY=qh ./render_en.sh
```

Cela produit une video silencieuse 1080p60 :

```text
final/kernel-intro-en-silent.mp4
```

### 6. Assembler audio + video

```bash
./assemble_en.sh
```

Resultat final :

```text
final/kernel-intro-en-final.mp4
```

Verification :

```bash
ffprobe -v error -show_entries format=duration,size -show_streams -of json final/kernel-intro-en-final.mp4
```

Attendu :

- video H.264
- 1920x1080
- 60 fps
- audio AAC mono
- duree audio et video quasiment identiques

### 7. Extraire des frames de controle

Toujours extraire les images une par une. Ne pas utiliser une commande multi-input avec plusieurs `-ss`, elle peut sortir plusieurs fois la meme frame.

```bash
mkdir -p renders
ffmpeg -y -ss 00:00:10 -i final/kernel-intro-en-final.mp4 -frames:v 1 -update 1 renders/check_0010.png
ffmpeg -y -ss 00:01:35 -i final/kernel-intro-en-final.mp4 -frames:v 1 -update 1 renders/check_0135.png
ffmpeg -y -ss 00:03:20 -i final/kernel-intro-en-final.mp4 -frames:v 1 -update 1 renders/check_0320.png
ffmpeg -y -ss 00:04:20 -i final/kernel-intro-en-final.mp4 -frames:v 1 -update 1 renders/check_0420.png
```

Inspecter visuellement les PNG. Chercher surtout :

- texte coupe par les bords
- mots trop longs dans des boites
- fleches ou labels qui se chevauchent
- scene qui reste trop longtemps sans changement
- scene vide ou quasi vide

## Pieges deja rencontres

### MP3 concatenes avec `-c copy`

Eviter de concatener directement des MP3 encodes separement avec `ffmpeg -c copy`. Cela peut produire des avertissements de timestamps non monotones et une duree globale fausse.

Solution actuelle : creer des WAV paddes par scene, concatener les WAV, puis encoder une seule fois le voiceover final.

### Padding video sans padding audio

Si Manim attend 0.45 s entre les scenes mais que l'audio global n'a pas ce silence, la video se decale progressivement.

Solution actuelle : `generate_voice_en.py` ajoute le meme padding dans les fichiers audio paddes et dans `durations.json`.

### Fade-out ajoute apres la duree cible

Si `finish_sync()` attend jusqu'a la duree audio, puis qu'on ajoute un fade-out de 0.7 s, chaque scene devient 0.7 s trop longue.

Solution actuelle : `finish_sync(trailing_animation=0.7)` retire le temps du fade-out final.

### Texte coupe en bord d'image

Verifier les PNG. Un bug a deja ete corrige dans la scene de memoire virtuelle : le mot `protected` etait coupe a droite.

## TTS local

Choix actuel :

- Chatterbox principal non-turbo : meilleur rendu vocal obtenu localement dans ce projet.
- Chatterbox Turbo : plus rapide, mais moins prefere par l'utilisateur.
- Kokoro : fallback rapide et leger.
- F5-TTS : option possible pour voix zero-shot, mais plus complexe.

Ne pas changer de modele final sans faire ecouter un echantillon a l'utilisateur.

## Commandes utiles

Depuis le dossier de la video :

```bash
python3 -m py_compile generate_voice_en.py kernel_intro_en.py
QUALITY=ql ./render_en.sh
QUALITY=qh ./render_en.sh
./assemble_en.sh
```

Depuis la racine du projet :

```bash
git status --short
find videos -maxdepth 3 -type f | sort
```

## Priorite si l'utilisateur demande une nouvelle video

1. Creer le nouveau dossier sous `videos/<thematique>/<numero-slug>/`.
2. Ecrire `plan.md`, `script.md`, puis `segments_en.json`.
3. Construire les scenes Manim en gardant une scene par segment audio.
4. Generer la voix Chatterbox principale.
5. Rendre basse qualite.
6. Corriger tous les problemes visuels et de synchronisation.
7. Rendre 1080p60.
8. Assembler audio/video.
9. Verifier avec `ffprobe` et snapshots.
10. Donner le chemin du MP4 final.

