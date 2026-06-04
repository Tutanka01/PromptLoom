# manim-video-voice-generator

Pipeline de generation de videos explicatives avec Manim, voix off TTS, synchronisation audio/video et assemblage final avec `ffmpeg`.

L'usage actuel du projet est la production de videos pedagogiques sur Linux, le noyau et les systemes bas niveau. L'objectif n'est pas de generer de simples prototypes Manim : chaque video doit etre construite comme une vraie video pedagogique, avec narration claire, scenes synchronisees avec la voix, rendu propre, verification technique et controle visuel avant livraison.

## Etat du projet

La video de reference actuelle est :

```text
videos/linux-fondamentaux/001-c-est-quoi-le-kernel/
```

Elle sert de modele pour l'organisation, la synchronisation audio/video, le rendu Manim et l'assemblage final avec `ffmpeg`.

Les fichiers generes lourds ne sont pas versionnes par defaut :

- `audio/`
- `final/`
- `media/`
- `renders/`
- fichiers `concat*.txt`

Le depot versionne surtout la recette reproductible : scripts, plans, narration, segments, scenes Manim et documentation.

## Documentation importante

Avant de modifier ou creer une video, lire :

```text
AGENTS.md
PROCEDURE.md
```

`AGENTS.md` definit les regles de qualite, les priorites et les comportements attendus.

`PROCEDURE.md` decrit le pipeline operationnel complet : generation de voix, synchronisation, rendu, assemblage et verification.

## Structure d'une video

Chaque video doit vivre dans son propre dossier :

```text
videos/<thematique>/<numero-slug>/
```

Exemple :

```text
videos/linux-fondamentaux/001-c-est-quoi-le-kernel/
```

Structure recommandee :

```text
plan.md                  # intention, public, scenes et logique pedagogique
script.md                # narration complete
segments_en.json         # segments synchronises avec les scenes
kernel_intro_en.py       # scenes Manim
generate_voice_en.py     # generation TTS
render_en.sh             # rendu Manim et concat video silencieuse
assemble_en.sh           # assemblage audio/video
audio/en/                # genere, ignore par git
final/                   # genere, ignore par git
renders/                 # controles visuels, ignore par git
```

Adapter les noms selon le sujet, mais garder la separation :

- narration ;
- segments ;
- scenes Manim ;
- voix ;
- rendu ;
- assemblage ;
- verification.

## Workflow de production

Le pipeline attendu est :

1. definir le sujet et le public ;
2. ecrire ou mettre a jour `plan.md` ;
3. ecrire le script narratif ;
4. decouper le script en segments ;
5. creer une classe Manim par segment ;
6. generer la voix off ;
7. produire `durations.json` ;
8. synchroniser les scenes sur les durees audio reelles ;
9. rendre en basse qualite ;
10. corriger les problemes de timing, texte et mise en scene ;
11. rendre en 1080p60 ;
12. assembler audio et video ;
13. verifier avec `ffprobe` ;
14. extraire et inspecter plusieurs frames ;
15. livrer le chemin du MP4 final.

Regle centrale : la voix et l'image doivent raconter exactement le meme segment pedagogique. Si la narration parle du scheduler, l'image montre le scheduler. Si elle parle de memoire virtuelle, l'image montre les adresses virtuelles, les tables de pages et la RAM.

## Audio

Le moteur de reference pour les videos finales anglaises est :

```text
Chatterbox principal non-turbo
```

Commande type depuis le dossier d'une video :

```bash
uv run --python 3.11 --with chatterbox-tts python generate_voice_en.py \
  --engine chatterbox \
  --exaggeration 0.45 \
  --cfg-weight 0.55 \
  --temperature 0.55 \
  --tail-padding 0.45
```

Le fichier cle de synchronisation est :

```text
audio/en/durations.json
```

Les scenes Manim doivent utiliser les memes cles que les segments audio.

## Rendu

Rendu de test :

```bash
QUALITY=ql ./render_en.sh
```

Rendu final :

```bash
QUALITY=qh ./render_en.sh
```

Le rendu final attendu est en 1080p60. Une scene qui echoue doit etre corrigee, pas supprimee sans modifier la narration.

## Assemblage

Depuis le dossier de la video :

```bash
./assemble_en.sh
```

Le fichier final doit etre ecrit dans :

```text
final/
```

Exemple :

```text
final/kernel-intro-en-final.mp4
```

## Verification

Verifier le fichier final avec :

```bash
ffprobe -v error -show_entries format=duration,size -show_streams -of json final/<video>.mp4
```

Points attendus :

- stream video present ;
- stream audio present ;
- resolution 1920x1080 ;
- framerate 60 fps ;
- audio AAC ;
- duree audio proche de la duree video ;
- pas de video muette ou anormalement courte.

Extraire ensuite plusieurs frames, une commande par timestamp :

```bash
mkdir -p renders
ffmpeg -y -ss 00:00:10 -i final/<video>.mp4 -frames:v 1 -update 1 renders/check_0010.png
ffmpeg -y -ss 00:01:30 -i final/<video>.mp4 -frames:v 1 -update 1 renders/check_0130.png
ffmpeg -y -ss 00:03:00 -i final/<video>.mp4 -frames:v 1 -update 1 renders/check_0300.png
```

Inspecter les images pour verifier :

- pas de texte coupe ;
- pas de labels hors cadre ;
- pas de chevauchements incoherents ;
- pas d'ecran vide ;
- pas de scene statique trop longtemps ;
- coherence entre ce qui est montre et ce qui est raconte.

## Darijat TTS

Le depot contient un petit test d'integration Darijat :

```text
generate_darijat_sample.py
darijat_sample_text.txt
```

La cle API doit rester dans `.env` :

```text
DARIJAT_API_TOKEN=...
```

`.env` est ignore par Git.

Generer un sample :

```bash
./generate_darijat_sample.py
```

Le sample MP3 genere a la racine est ignore par Git. Pour les scripts arabes, la strategie actuelle est d'ecrire un texte en arabe standard clair, puis de laisser la voix marocaine apporter la couleur vocale.

## Strategie Git

Ce depot doit rester centre sur les sources reproductibles.

A versionner :

- plans ;
- scripts narratifs ;
- fichiers de segments ;
- scenes Manim ;
- scripts de generation audio ;
- scripts de rendu et assemblage ;
- documentation.

A ne pas versionner :

- secrets `.env` ;
- caches Python ;
- sorties Manim ;
- voix generees ;
- videos finales ;
- snapshots de verification ;
- fichiers temporaires de concat.

Avant de committer :

```bash
git status --short --ignored
git ls-files --others --exclude-standard
```

Puis :

```bash
git add -A
git commit -m "Add kernel video generation pipeline"
```

## Dependances

Outils utilises dans le pipeline :

- Python 3.11 pour la generation TTS ;
- `uv` pour lancer les dependances Python ponctuelles ;
- Manim Community Edition ;
- `ffmpeg` et `ffprobe` ;
- Chatterbox TTS pour la voix locale de reference ;
- API Darijat TTS pour les tests de voix arabe/marocaine.

Installer ou verifier ces dependances selon la machine avant de lancer un rendu complet.
