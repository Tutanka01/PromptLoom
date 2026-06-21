# PromptLoom Video API Documentation

Cette documentation décrit l'application principale du dépôt, située dans
`apps/video-api/`.

Le but de cette application est de recevoir un prompt utilisateur, creer un job asynchrone, produire les sources de video, generer la voix, rendre Manim, assembler le MP4, verifier la qualite, puis exposer un lien de telechargement.

## Guides

- [Commencer avec PromptLoom](../../../docs/START_HERE.md): orientation depuis la racine du dépôt.
- [Première vidéo](../../../docs/FIRST_VIDEO.md): tutoriel complet, de `.env` au MP4.
- [Quickstart](quickstart.md): lancer l'API avec Docker et creer une video avec `curl`.
- [Architecture](architecture.md): services, pipeline, et cycle de vie d'un job.
- [API Reference](api-reference.md): endpoints HTTP, schemas de requetes et reponses.
- [Developer Guide](developer-guide.md): comment travailler sur le code, ajouter une etape ou changer le generateur.
- [Operations](operations.md): variables d'environnement, Docker, tests, logs, volumes, depannage.
- [LLM Contract](llm-contract.md): contrat attendu entre le worker et un endpoint compatible OpenAI.
- [Remotion Engine](remotion-engine.md): moteur de rendu Remotion (`VIDEO_API_RENDER_ENGINE=remotion`), alternative a Manim partageant TTS/assemble/verify.
- [Production avancee](advanced-production.md): recherche sourcee, medias locaux, captions, motion design, son et gate anti-diaporama activables par requete.

## Principe important

L'API est le produit principal. Elle automatise et généralise les enseignements
du pipeline vidéo manuel historique :

```text
prompt
  -> recherche sourcee optionnelle
  -> proposition + blueprint LLM structure
  -> scene plan + gate de mouvement
  -> plan/script/segments/beats
  -> code Manim ou Remotion
  -> voix Chatterbox
  -> rendu + captions alignees
  -> assemblage ffmpeg
  -> verification ffprobe/freezedetect/snapshots
  -> MP4 final
```

Le pipeline manuel existant dans `videos/...` reste utilisable comme référence
et banc d'essai. Les jobs API sont écrits dans le volume d'artefacts de
l'application, pas directement dans les dossiers sources suivis par Git.

## Etat actuel

Cette v1 pose une base transportable par Docker :

- API FastAPI.
- Worker Celery.
- Redis comme broker.
- Postgres pour les metadonnees de jobs.
- Volume Docker partage pour les artefacts.
- Endpoint LLM compatible OpenAI configurable.
- Worker de rendu limite a une concurrence de 1 par defaut.

Les tests valides actuellement couvrent la structure Python, la validation de schemas, le build Docker, le demarrage API, et la creation de jobs. Un rendu complet Chatterbox + Manim reste un test long a lancer volontairement.
