# Standard historique de production vidéo manuelle v2

> Ce standard s'applique aux productions manuelles conservées dans `videos/`.
> La plateforme principale est `apps/video-api`, qui automatise ces principes et
> possède sa propre documentation dans `apps/video-api/docs/`.

Ce document decrit la nouvelle facon de produire les videos du projet : narration structuree, voix locale, synchro audio reelle, beats narratifs, design system Manim, rendu final et controles qualite.

Il complete `PROCEDURE.md`. `PROCEDURE.md` donne l'ordre operationnel. Ce document donne le niveau de detail attendu pour produire une video vraiment montrable.

Toute documentation reusable doit rester a la racine ou dans `docs/`. Les dossiers `videos/...` ne doivent pas contenir de README, notes de voix, guides operationnels, plan narratif ou script narratif. Ils gardent seulement les sources de production propres a la video : segments, beats, code Manim, scripts de rendu, final approuve.

Les plans et scripts narratifs vivent dans :

```text
docs/videos/<theme>/<slug>/
```

## Objectif

Produire des videos pedagogiques sur Linux et les systemes bas niveau qui soient :

- claires dans la narration ;
- synchronisees avec la voix ;
- visuellement lisibles ;
- techniquement verifiees ;
- reproductibles par un autre agent ;
- assez propres pour etre montrees comme des videos finales.

La cible n'est pas un prototype. Un rendu final doit pouvoir etre partage sans devoir expliquer ses defauts.

## References internes

Reference pipeline historique :

```text
videos/linux-fondamentaux/001-c-est-quoi-le-kernel/
```

Reference standard v2 :

```text
videos/linux-fondamentaux/002-c-est-quoi-un-syscall/
```

Dans la video syscall, les deux scenes pilotes montrent le nouveau niveau attendu :

- `Scene1_HookEN` : commande, chemin direct bloque, gate syscall, kernel, storage ;
- `Scene2_PrivilegeBoundaryEN` : user mode, kernel mode, saut bloque, entree CPU controlee, retour.

## Idee centrale du standard v2

Avant, la synchronisation etait surtout :

```text
duree audio de scene -> duree totale Manim
```

Maintenant, elle devient :

```text
duree audio de scene -> beats narratifs -> actions visuelles
```

`durations.json` reste la source de verite pour la duree totale. `beats_en.json` donne les points interieurs ou l'image doit changer pour accompagner la phrase entendue.

Une scene peut etre parfaitement alignee en duree et pourtant mauvaise si elle reste figee pendant que la voix continue. Le standard v2 corrige ce probleme.

## Documents et sources obligatoires par video

### `docs/videos/<theme>/<slug>/plan.md`

Role : decrire l'intention pedagogique et le plan visuel.

Contenu attendu :

- topic ;
- audience ;
- pre-requis ;
- duree cible ;
- insight principal ;
- arc narratif ;
- scene breakdown ;
- visual rules ;
- beat-sync standard ;
- design standard ;
- verification standard ;
- risques ;
- definition de fini.

Question a se poser : si quelqu'un lit seulement ce `plan.md`, peut-il comprendre ce que la video doit enseigner et comment elle doit le montrer ?

### `docs/videos/<theme>/<slug>/script.md` ou `script_en.md`

Role : narration humaine, scene par scene.

Regles :

- une section par scene ;
- phrases courtes et orales ;
- transitions explicites ;
- pas de jargon non introduit ;
- pas de concept visuel absent de la scene correspondante ;
- ne pas changer ce fichier apres validation audio sans raison forte.

### `segments_en.json`

Role : source de verite pour le TTS.

Schema :

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

- `key` = `class` = `scene_key` dans Manim ;
- l'ordre du JSON est l'ordre final ;
- une entree = un fichier audio scene ;
- ne pas melanger plusieurs scenes dans un segment ;
- ne pas supprimer une scene sans adapter le script, le rendu et le concat.

### `beats_en.json`

Role : mapper les moments de narration aux actions visuelles.

Schema :

```json
{
  "Scene1_HookEN": [
    {
      "key": "command",
      "at": 0.08,
      "text_hint": "Run a tiny command.",
      "visual_action": "Reveal the terminal command."
    }
  ]
}
```

Champs :

- `key` : identifiant stable du beat ;
- `at` : ratio de la duree audio de la scene, entre `0.0` et `1.0` ;
- `text_hint` : phrase ou idee entendue a ce moment ;
- `visual_action` : action precise a l'ecran.

Qualite attendue :

- 5 a 7 beats pour une scene dense ;
- 3 a 4 beats acceptables pour une scene tres courte ;
- dernier beat utile vers 0.80 a 0.90 ;
- pas de beat flou ;
- pas d'action visuelle deconnectee du texte entendu.

Mauvais beat :

```json
{
  "key": "stuff",
  "at": 0.50,
  "text_hint": "More explanation.",
  "visual_action": "Make it nicer."
}
```

Bon beat :

```json
{
  "key": "blocked_jump",
  "at": 0.56,
  "text_hint": "If a program could just jump into kernel memory...",
  "visual_action": "Animate a direct jump from user mode and block it at the privilege boundary."
}
```

### `<slug>_style.py`

Role : design system local.

Doit contenir :

- palette ;
- tailles de texte ;
- helpers `t` et `mono` ;
- fond ;
- cartes ;
- boites hardware ;
- connecteurs ;
- helpers `focus`, `dim`, `undim`, `glow` ;
- helpers de flux comme `flow_dot`.

Objectif : les scenes doivent utiliser un langage visuel commun, pas re-dessiner chaque boite a la main.

### `<slug>_en.py`

Role : scenes Manim synchronisees.

Doit contenir :

- chargement de `durations.json` ;
- chargement de `segments_en.json` pour sous-titres ;
- chargement optionnel de `beats_en.json` ;
- classe de base avec helpers de synchro ;
- une classe Manim par segment ;
- pas de logique TTS ;
- pas de chemins absolus.

### `generate_voice_en.py`

Role : generer ou reutiliser la voix locale.

Doit :

- lire `segments_en.json` ;
- produire un audio par scene ;
- produire des WAV paddes ;
- produire `audio/en/durations.json` ;
- produire `voiceover_en.wav` et `voiceover_en.mp3` ;
- eviter de regenerer les WAV existants sauf option explicite.

### `render_en.sh`

Role : rendre toutes les scenes et creer la video silencieuse.

Doit :

- definir l'ordre des scenes ;
- accepter `QUALITY=ql` et `QUALITY=qh` ;
- lancer Manim Community Edition ;
- produire `concat_en.txt` ;
- produire `final/<slug>-en-silent.mp4`.

### `assemble_en.sh`

Role : muxer video silencieuse + audio global.

Doit :

- prendre `final/<slug>-en-silent.mp4` ;
- prendre `audio/en/voiceover_en.mp3` ;
- produire `final/<slug>-en-final.mp4` ;
- encoder l'audio final en AAC.

## Classe de base de synchronisation

Chaque video doit avoir une classe de base proche de ce pattern :

```python
class EnglishVideoScene(Scene):
    scene_key = ""
    fallback_duration = 35.0

    def begin_sync(self):
        self._sync_start = self.time
        self._scene_duration = duration(self.scene_key, self.fallback_duration)
        text = SEGMENT_TEXT.get(self.scene_key)
        if text:
            self.add_subcaption(text, duration=self._scene_duration)

    def scene_duration(self):
        return getattr(self, "_scene_duration", duration(self.scene_key, self.fallback_duration))

    def cue(self, ratio):
        return self._sync_start + self.scene_duration() * ratio

    def hold_until(self, ratio):
        self.wait(max(0, self.cue(ratio) - self.time))

    def play_until(self, ratio, *animations, min_run_time=0.25, rate_func=smooth):
        run_time = max(min_run_time, self.cue(ratio) - self.time)
        self.play(*animations, run_time=run_time, rate_func=rate_func)

    def finish_sync(self, trailing_animation=0.7):
        target = self.scene_duration()
        elapsed = self.time - self._sync_start
        self.wait(max(0, target - elapsed - trailing_animation))
```

Regles :

- `begin_sync()` au debut du `construct()` ;
- `finish_sync()` juste avant le fade-out final ;
- `play_until()` pour les actions principales ;
- `hold_until()` seulement si l'image doit volontairement rester stable ;
- aucun long `wait()` arbitraire ;
- si `play_until()` calcule un temps tres long, ajouter un beat intermediaire.

## Ecriture d'une scene v2

Une bonne scene v2 a :

- une question visuelle claire ;
- un point de depart reconnaissable ;
- une progression ;
- un element actif ;
- un retour ou une conclusion ;
- une sortie propre.

Exemple de squelette :

```python
class Scene1_HookEN(EnglishVideoScene):
    scene_key = "Scene1_HookEN"
    fallback_duration = 35

    def construct(self):
        self.begin_sync()

        bg = make_background()
        title = title_bar("A command is not direct")
        command = code_card("$ cat notes.txt")
        app = card("program")
        gate = card("syscall gate")
        kernel = kernel_badge("KERNEL")
        storage = hardware_box("storage", "NVMe")

        self.add(bg)
        self.play_until(0.08, FadeIn(title), FadeIn(command))
        self.play_until(0.24, FadeIn(app), FadeIn(storage))
        self.play_until(0.38, FadeIn(blocked_direct_path))
        self.play_until(0.68, FadeIn(gate), FadeIn(kernel), Create(path))
        self.play_until(0.88, MoveAlongPath(token, path), FadeIn(summary))

        self.finish_sync()
        self.play(FadeOut(fade_group(bg, title, command, app, gate, kernel, storage, path, summary)), run_time=0.7)
```

## Visual design checklist

Avant de rendre :

- la scene tient en 16:9 sans zoom mental ;
- les labels restent dans leurs boites ;
- aucune boite ne depend d'un texte trop long ;
- les fleches partent et arrivent sur des bords propres ;
- les zones user/kernel/hardware sont identifiables ;
- la palette n'est pas un seul camaieu ;
- le texte fonctionnel utilise plutot `FadeIn` que `Write` ;
- les titres ne prennent pas trop de place ;
- les objets importants ne se recouvrent pas ;
- le spectateur sait ou regarder.

Pendant l'animation :

- un seul element actif a la fois ;
- le reste peut etre dimme ;
- les tokens de flux montrent le trajet ;
- les changements arrivent au moment ou la voix en parle ;
- aucune longue queue statique non intentionnelle.

## Limites de densite

Regle pratique :

- 1 titre ;
- 3 a 5 objets principaux ;
- 1 a 3 labels secondaires ;
- 1 chemin ou groupe de fleches ;
- 1 summary maximum.

Si la scene depasse environ 7 elements importants visibles, utiliser progressive disclosure ou separer en deux scenes.

## Controle audio

Apres generation :

```bash
cat audio/en/durations.json
ffprobe -v error -show_entries format=duration -of default=nk=1:nw=1 audio/en/voiceover_en.mp3
```

Verifier :

- chaque `scene_key` a une duree ;
- pas de duree a zero ;
- la somme des durees correspond au voiceover global ;
- les WAV ne sont pas regeneres sans demande ;
- le padding de fin est inclus dans l'audio et dans `durations.json`.

## Controle basse qualite

Depuis le dossier video :

```bash
QUALITY=ql ./render_en.sh
./assemble_en.sh
```

Puis :

```bash
ffprobe -v error -show_entries format=duration,size -show_streams -of json final/<slug>-en-final.mp4
ffmpeg -i final/<slug>-en-final.mp4 -vf freezedetect=n=-60dB:d=3 -an -f null -
```

Le rendu basse qualite sert a detecter :

- erreurs Manim ;
- textes coupes ;
- timing mort ;
- scene trop dense ;
- scene sans rapport avec la voix ;
- probleme d'assemblage audio/video.

## Snapshots obligatoires

Extraire des snapshots :

- debut de video ;
- scene pilote a 30% ;
- scene pilote a 60% ;
- scene pilote a 90% ;
- milieu de video ;
- scene dense ;
- scene finale.

Commandes :

```bash
mkdir -p renders/final_checks
ffmpeg -y -ss 00:00:10 -i final/<slug>-en-final.mp4 -frames:v 1 -update 1 renders/final_checks/check_0010.png
ffmpeg -y -ss 00:01:30 -i final/<slug>-en-final.mp4 -frames:v 1 -update 1 renders/final_checks/check_0130.png
ffmpeg -y -ss 00:03:00 -i final/<slug>-en-final.mp4 -frames:v 1 -update 1 renders/final_checks/check_0300.png
```

Pour les scenes pilotes, extraire aussi a des timestamps correspondant a 30%, 60%, 90% de la scene.

Inspection :

- regarder les images, pas seulement les logs ;
- verifier la lisibilite a taille normale ;
- verifier que le focus est clair ;
- verifier que le moment visuel correspond a la narration ;
- corriger et re-rendre si un snapshot montre un label casse.

## Freezedetect

Commande detaillee :

```bash
ffmpeg -i final/<slug>-en-final.mp4 -vf freezedetect=n=-60dB:d=3 -an -f null -
```

Commande resume :

```bash
ffmpeg -i final/<slug>-en-final.mp4 -vf freezedetect=n=-60dB:d=3 -an -f null - 2>&1 \
  | awk '/freeze_duration/ {count += 1; total += $NF} END {printf "freezes=%d total=%.2f avg=%.2f\n", count, total, (count ? total/count : 0)}'
```

Interpretion :

- `freezes=0` sur les scenes pilotes est excellent ;
- une video complete peut garder quelques pauses, mais elles doivent etre justifiees ;
- comparer le total a la baseline precedente ;
- si une scene depasse 4 a 6 secondes figees sans intention, ajouter des beats ou refaire le visuel.

## Controle final 1080p60

Rendu :

```bash
QUALITY=qh ./render_en.sh
./assemble_en.sh
```

Verification :

```bash
ffprobe -v error -show_entries format=duration,size -show_streams -of json final/<slug>-en-final.mp4
```

Attendu :

- `codec_type=video` ;
- `codec_name=h264` ;
- `width=1920` ;
- `height=1080` ;
- `r_frame_rate=60/1` ;
- `codec_type=audio` ;
- `codec_name=aac` ;
- audio mono accepte ;
- duree audio proche de la duree video.

Tolerance :

- difference audio/video idealement sous 0.25 s ;
- sous 1 s acceptable si le rendu visuel ne montre pas de decalage ;
- au-dela, diagnostiquer le padding, le fade-out ou l'assemblage.

## Git et fichiers generes

A garder :

- plans ;
- scripts ;
- segments ;
- beats ;
- code Manim ;
- style ;
- generateurs ;
- scripts render/assemble ;
- README ;
- final MP4 approuve si choisi.

A ignorer ou ne pas ajouter par defaut :

- `audio/en/*.wav` ;
- caches Manim ;
- snapshots temporaires ;
- concat temporaire ;
- silent MP4 si le projet decide de ne garder que le final.

Avant de finir :

```bash
git status --short
```

Ne jamais pretendre que le depot est propre si ce n'est pas le cas.

## Definition de qualite excellente

Une video est excellente quand :

- le hook est comprehensible en moins de 20 secondes ;
- chaque scene a un role pedagogique clair ;
- les beats suivent la phrase entendue ;
- les visuels ne sont ni generiques ni decoratifs ;
- les figures sont propres, alignees et lisibles ;
- la densite est maitrisee ;
- les transitions ont du sens ;
- l'audio est agreable et non robotique ;
- le final est 1080p60 avec audio AAC ;
- les snapshots ne revelent pas de probleme cache ;
- les limites restantes sont connues et documentees.

## Checklist finale

Avant livraison, cocher mentalement :

- `docs/videos/<theme>/<slug>/plan.md` a jour ;
- `docs/videos/<theme>/<slug>/script.md` a jour ;
- `segments_en.json` coherent ;
- `beats_en.json` coherent ;
- voix generee ou reutilisee volontairement ;
- `durations.json` present ;
- scenes Manim synchronisees par helpers ;
- design system utilise ;
- rendu basse qualite fait ;
- assemblage basse qualite fait ;
- `ffprobe` fait ;
- `freezedetect` fait ;
- snapshots inspectes ;
- rendu 1080p60 fait ;
- assemblage final fait ;
- `ffprobe` final fait ;
- snapshots finaux inspectes ;
- `git status --short` consulte ;
- chemin final communique.
