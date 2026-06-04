# Voix off locale

## Objectif qualite
Pour la version finale, il faut viser une voix française expressive, stable sur 5 minutes, avec peu d'artefacts sur les mots techniques : kernel, syscall, scheduler, namespaces, cgroups.

## Backends locaux prévus

### 1. Modèle local haute qualité
À privilégier pour la version finale. Le script `generate_voice.py` est volontairement séparé du rendu vidéo pour pouvoir brancher un moteur local plus haut de gamme sans toucher à Manim.

Critères :
- inférence locale ;
- voix française ou clonage/licence compatible ;
- export WAV/MP3 ;
- contrôle du débit et des pauses ;
- pas de dépendance cloud pour le rendu final.

### 2. Piper local
Bon fallback entièrement local, simple à automatiser, mais souvent moins naturel qu'un modèle neural plus récent. Utilisable avec :

```bash
python3 generate_voice.py --engine piper --piper-model /path/to/model.onnx
```

### 3. Voix macOS locale
Fallback de maquette, pas le rendu final recommandé :

```bash
python3 generate_voice.py --engine macos --voice Thomas --rate 155
```

Ce backend génère `audio/voiceover.mp3` si `afconvert` sait encoder MP3 sur la machine. Il génère aussi `audio/voiceover.aiff`.
