# C'est quoi le kernel Linux ?

Production Manim d'une video d'environ 5 minutes sur le kernel Linux.

## Fichiers
- `plan.md` : storyboard scene par scene.
- `script.md` : script narratif lisible.
- `voiceover.txt` : texte brut utilise par les moteurs TTS.
- `kernel_intro.py` : scenes Manim.
- `generate_voice.py` : generation de voix locale.
- `render.sh` : rendu Manim et assemblage video silencieuse.
- `assemble.sh` : mux video + audio.

## Commandes

```bash
cd videos/linux-fondamentaux/001-c-est-quoi-le-kernel
python3 generate_voice.py --engine macos --voice Thomas --rate 155
QUALITY=qm ./render.sh
AUDIO=audio/voiceover.aiff ./assemble.sh
```

Pour une voix finale locale de meilleure qualite, remplace `audio/voiceover.*` par une piste generee avec un moteur neural local, puis relance `assemble.sh`.
