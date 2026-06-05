# AGENTS.md

Ce fichier s'adresse a toute IA ou tout agent de code qui reprend ce projet.

Avant de modifier quoi que ce soit, lire aussi :

```text
PROCEDURE.md
docs/VIDEO_PRODUCTION_STANDARD.md
```

`PROCEDURE.md` contient le pipeline operationnel detaille. `docs/VIDEO_PRODUCTION_STANDARD.md` contient le standard v2 complet : beats narratifs, design system, controles de fluidite et criteres d'acceptation. Ce fichier-ci fixe les regles de comportement, les priorites et les standards attendus.

La documentation reusable doit rester a la racine ou dans `docs/`. Ne pas ajouter de README, notes de voix ou documentation operationnelle dans les dossiers `videos/...`; ces dossiers ne doivent contenir que les sources de production de la video.

## Mission du projet

Produire des videos explicatives de haute qualite sur Linux et les systemes bas niveau, avec :

- animations Manim propres, lisibles et synchronisees ;
- narration structuree scene par scene ;
- voix off locale de qualite, actuellement Chatterbox principal non-turbo ;
- rendu final assemble avec ffmpeg ;
- verification visuelle et technique avant livraison.

Le resultat attendu n'est pas un simple prototype. Chaque video doit pouvoir etre montree comme une vraie video pedagogique.

## Point de reference

La video de reference actuelle est :

```text
videos/linux-fondamentaux/001-c-est-quoi-le-kernel/final/kernel-intro-en-final.mp4
videos/linux-fondamentaux/002-c-est-quoi-un-syscall/final/syscall-intro-en-final.mp4
```

La premiere sert d'exemple pour :

- l'organisation des dossiers ;
- la separation script / segments / scenes Manim / audio / final ;
- le choix Chatterbox principal non-turbo ;
- la synchronisation par durees audio reelles ;
- les verifications avec `ffprobe` et snapshots.

La seconde sert d'exemple pour le standard v2 :

- `beats_en.json` ;
- synchro interne avec `cue()`, `play_until()` et `hold_until()` ;
- design system local dans `syscall_style.py` ;
- focus/dim plutot que surlignage permanent ;
- validation avec `freezedetect` et snapshots.

## Regle principale

Ne jamais produire une video ou la voix et l'image semblent raconter deux sujets differents.

Chaque segment audio doit correspondre a une scene Manim precise. Si la narration parle de scheduler, l'image doit montrer le scheduler. Si la narration parle de virtual memory, l'image doit montrer les adresses virtuelles, les page tables et la RAM. Si ce lien n'est pas clair, la scene doit etre repensee.

## Structure obligatoire

Toute nouvelle video doit etre creee dans :

```text
videos/<thematique>/<numero-slug>/
```

Exemple :

```text
videos/linux-fondamentaux/002-c-est-quoi-un-syscall/
```

Ne pas mettre les fichiers d'une nouvelle video a la racine du projet.

Structure documentation recommandee :

```text
docs/videos/<thematique>/<numero-slug>/
plan.md
script.md ou script_en.md
```

Structure production recommandee :

```text
segments_en.json
beats_en.json
kernel_intro_en.py
kernel_style.py
generate_voice_en.py
render_en.sh
assemble_en.sh
audio/en/
final/
renders/
```

Adapter les noms Python si le sujet n'est plus `kernel_intro`, mais garder le meme principe.

Pour demarrer une nouvelle video, copier le boilerplate depuis :

```text
docs/boilerplate/
```

## Workflow obligatoire

1. Comprendre le sujet et le public vise.
2. Ecrire ou mettre a jour `docs/videos/<thematique>/<numero-slug>/plan.md`.
3. Ecrire le script narratif dans `docs/videos/<thematique>/<numero-slug>/script.md`.
4. Decouper le script dans `segments_en.json`.
5. Creer `beats_en.json` pour relier narration et actions visuelles.
6. Creer une classe Manim par segment audio.
7. Creer ou mettre a jour le design system local.
8. Generer la voix off locale.
9. Produire `durations.json`.
10. Synchroniser les scenes avec les durees audio et les beats narratifs.
11. Rendre en basse qualite.
12. Assembler l'audio et la video basse qualite.
13. Mesurer `ffprobe`, `freezedetect`, puis inspecter les snapshots.
14. Corriger les problemes de narration, timing et visuel.
15. Rendre en 1080p60.
16. Assembler l'audio et la video finale.
17. Refaire `ffprobe`, `freezedetect` et les snapshots finaux.
18. Donner le chemin du MP4 final.

Ne pas sauter les etapes de verification.

## Audio et voix

Le modele prefere est :

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

- Ne pas utiliser `say` macOS pour une version finale.
- Ne pas remplacer Chatterbox principal par Turbo sans demander a l'utilisateur.
- Ne pas regenerer une voix deja acceptee sans raison.
- Si `generate_voice_en.py` sait reutiliser les WAV existants, le laisser faire.
- Si un segment change, regenerer seulement ce qui doit changer quand c'est possible.

La lenteur de Chatterbox principal est acceptable. L'utilisateur a explicitement prefere cette version a Turbo.

## Synchronisation v2

La synchro doit etre conduite par les durees audio, pas par intuition.

Le fichier cle est :

```text
audio/en/durations.json
```

Pour les videos v2, ajouter aussi :

```text
beats_en.json
```

`durations.json` fixe la duree totale de chaque scene. `beats_en.json` decrit les moments internes de narration ou l'image doit changer.

Chaque scene Manim doit utiliser une cle qui correspond a un segment :

```python
class SceneX_NameEN(EnglishKernelScene):
    scene_key = "SceneX_NameEN"
```

Pattern attendu :

```python
self.begin_sync()
# animations de la scene
self.finish_sync()
self.play(FadeOut(...), run_time=0.7)
```

Pattern v2 attendu pour les scenes nouvelles ou refondues :

```python
self.begin_sync()
self.play_until(0.08, FadeIn(title))
self.play_until(0.25, FadeIn(first_visual))
self.play_until(0.52, Transform(...))
self.hold_until(0.72)
self.play_until(0.88, FadeIn(summary))
self.finish_sync()
self.play(FadeOut(...), run_time=0.7)
```

Attention : `finish_sync()` doit tenir compte du fade-out final. Voir l'implementation existante dans :

```text
videos/linux-fondamentaux/001-c-est-quoi-le-kernel/kernel_intro_en.py
videos/linux-fondamentaux/002-c-est-quoi-un-syscall/syscall_intro_en.py
```

Regles :

- ne pas ajouter des `wait()` aleatoires qui cassent la synchro ;
- viser 5 a 7 beats par scene importante ;
- faire evoluer l'image jusqu'a environ 80-90% de la narration ;
- eviter les longues attentes finales comme solution de synchronisation ;
- utiliser `FadeIn` pour les labels fonctionnels si `Write` produit du texte partiellement dessine sur snapshots.

## Video et Manim

Utiliser Manim Community Edition, pas ManimGL.

Import attendu :

```python
from manim import *
```

Rendu de test :

```bash
QUALITY=ql ./render_en.sh
```

Rendu final :

```bash
QUALITY=qh ./render_en.sh
```

Le rendu final attendu est 1080p60.

Si une scene echoue, corriger la scene et relancer. Ne pas contourner l'erreur en supprimant la scene sauf si le script narratif est modifie en consequence.

Design attendu :

- utiliser un fichier style local ;
- garder une typographie lisible ;
- limiter la densite ;
- utiliser focus/dim/flux pour guider l'attention ;
- eviter les schemas generiques sans lien avec la phrase entendue.

## Assemblage

Assembler avec :

```bash
./assemble_en.sh
```

Le resultat final doit etre dans :

```text
final/
```

Nommer clairement les fichiers finaux, par exemple :

```text
final/kernel-intro-en-final.mp4
```

ou pour une nouvelle video :

```text
final/syscall-intro-en-final.mp4
```

## Verifications obligatoires

Apres assemblage final :

```bash
ffprobe -v error -show_entries format=duration,size -show_streams -of json final/<video>.mp4
```

Verifier :

- presence d'un stream video ;
- presence d'un stream audio ;
- resolution 1920x1080 ;
- framerate 60 fps ;
- duree audio proche de la duree video ;
- absence de video anormalement courte ou muette.

Extraire plusieurs snapshots :

```bash
mkdir -p renders
ffmpeg -y -ss 00:00:10 -i final/<video>.mp4 -frames:v 1 -update 1 renders/check_0010.png
ffmpeg -y -ss 00:01:30 -i final/<video>.mp4 -frames:v 1 -update 1 renders/check_0130.png
ffmpeg -y -ss 00:03:00 -i final/<video>.mp4 -frames:v 1 -update 1 renders/check_0300.png
```

Mesurer aussi la fluidite :

```bash
ffmpeg -i final/<video>.mp4 -vf freezedetect=n=-60dB:d=3 -an -f null -
```

Ouvrir les images et verifier :

- pas de texte coupe ;
- pas de labels hors cadre ;
- pas de chevauchements incoherents ;
- pas d'ecran vide ;
- pas de scene visuellement statique trop longtemps ;
- les images correspondent au sujet parle a ce moment.

## Pieges connus

Lire `PROCEDURE.md` pour le detail, mais retenir surtout :

- ne pas concatener directement des MP3 separes avec `-c copy` ;
- ne pas ajouter du padding video sans le meme padding audio ;
- ne pas oublier que le fade-out final allonge la scene ;
- ne pas faire confiance au rendu sans snapshots ;
- ne pas faire confiance a une scene dont la duree est correcte mais dont l'image reste figee ;
- ne pas utiliser une commande ffmpeg multi-input pour extraire plusieurs timestamps, elle peut sortir plusieurs fois la meme frame.

## Travail dans le depot

Le projet peut contenir des fichiers non suivis ou des changements utilisateur.

Regles :

- Ne pas supprimer ou reinitialiser des fichiers sans demande explicite.
- Ne pas faire de `git reset --hard`.
- Ne pas nettoyer `videos/` ou `media/` sans accord.
- Ajouter les fichiers utiles au bon endroit.
- Eviter les refactors qui ne servent pas directement la video.

Avant de finir, consulter :

```bash
git status --short
```

Ne pas pretendre que tout est commit ou propre si ce n'est pas le cas.

## Sources et recherche

Si la demande concerne un choix de modele, une bibliotheque ou un outil qui peut evoluer, verifier l'information en ligne.

Pour les TTS locaux/open-source, les references deja utilisees sont :

- Chatterbox : https://github.com/resemble-ai/chatterbox
- Kokoro : https://github.com/hexgrad/kokoro
- F5-TTS : https://github.com/SWivid/F5-TTS

Pour Manim, preferer la documentation Manim Community Edition et les patterns deja presents dans ce depot.

## Quand demander a l'utilisateur

Demander confirmation seulement si le choix change vraiment le resultat :

- changer de langue ;
- changer de voix ou de modele TTS ;
- raccourcir fortement la video ;
- supprimer une scene ;
- remplacer Chatterbox principal par un autre modele ;
- faire une action destructive.

Sinon, avancer avec les conventions existantes.

## Definition de "termine"

Une video est terminee seulement si :

- le script est present ;
- les segments audio sont presents ;
- `beats_en.json` est present pour les scenes v2 ou pilotes ;
- le fichier audio global est present ;
- le rendu video silencieux est present ;
- le MP4 final audio+video est present ;
- `ffprobe` confirme audio et video ;
- `freezedetect` a ete mesure ;
- plusieurs frames ont ete inspectees ;
- le chemin final est donne a l'utilisateur.

Si une de ces conditions manque, dire clairement ce qui manque.
