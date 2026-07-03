# Quickstart

Ce guide montre comment lancer l'API et creer un job video depuis un terminal.

Pour un parcours plus guidé avec diagnostic, suivi des erreurs et choix de
moteur, voir aussi [Créer sa première vidéo](../../../docs/FIRST_VIDEO.md).

## 1. Configurer l'environnement

Depuis la racine du depot :

```bash
cp apps/video-api/.env.example .env
```

Edite `.env` pour pointer vers ton endpoint compatible OpenAI :

```text
OPENAI_BASE_URL=http://ton-serveur-llm/v1
OPENAI_API_KEY=ta-cle-ou-placeholder-local
OPENAI_MODEL=nom-du-modele
```

Pour tester sans endpoint LLM reel :

```text
VIDEO_API_FAKE_LLM=1
```

Ce mode genere un blueprint factice. Il sert a tester l'API et le pipeline sans appeler de modele.

## 2. Lancer l'API

```bash
docker compose up --build
```

Le `compose.yaml` de la racine est le point d'entree principal. Le fichier
`apps/video-api/compose.yaml` reste utilisable directement pour travailler
uniquement dans ce composant.

Services lances :

- `api`: serveur HTTP sur `http://localhost:8080`.
- `worker`: worker Celery qui execute les jobs.
- `redis`: broker de queue.
- `postgres`: base de metadonnees.

Verifie que l'API repond :

```bash
curl http://localhost:8080/healthz
```

Reponse attendue :

```json
{"status":"ok"}
```

## 3. Creer une video

```bash
curl -X POST http://localhost:8080/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Make a short video explaining derivatives intuitively","theme":"math"}'
```

Pour demander une video dans une autre langue, ajoute `language` :

```bash
curl -X POST http://localhost:8080/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Explique ce qu est un syscall Linux","theme":"cs","language":"fr"}'
```

Exemple plus complet : prompt en francais, video finale en italien, duree cible
4 minutes, profil production :

```bash
curl -X POST http://localhost:8080/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Explique pourquoi un programme utilisateur Linux passe par un appel systeme pour lire un fichier",
    "theme": "linux-fondamentaux",
    "language": "it",
    "target_duration_seconds": 240,
    "quality_profile": "standard"
  }'
```

Parametres utiles :

- `language` choisit la langue de sortie, pas la langue du prompt. Exemple :
  `language: "it"` produit narration et textes visibles en italien, meme avec un
  prompt en francais.
- `target_duration_seconds` est une cible de duree entre 20 et 900 secondes. La
  duree finale depend ensuite des WAV TTS reels et de `audio/en/durations.json`.
- `quality_profile` vaut `standard` par defaut. `draft` est plus rapide mais force
  Kokoro et convient surtout a EN/FR. Pour les autres langues europeennes, utilise
  `standard` avec `VIDEO_API_VOICE_ENGINE=moss`. `high` ajoute la revue visuelle si
  un modele vision est configure. `final` est un alias historique de `standard`.

Reponse :

```json
{
  "job_id": "c52681fd-6cd3-4538-9a2f-c5a199186585",
  "status_url": "/v1/videos/c52681fd-6cd3-4538-9a2f-c5a199186585",
  "download_url": null
}
```

Le `job_id` est l'identifiant a garder cote client.

## 4. Suivre le job

```bash
curl http://localhost:8080/v1/videos/<job_id>
```

Exemple de reponse :

```json
{
  "job_id": "<job_id>",
  "status": "queued",
  "progress": 0,
  "current_step": "queued",
  "error_message": null,
  "download_url": null,
  "report_url": null
}
```

Quand le job est termine, `status` vaut `completed` et `download_url` est disponible.

## 5. Telecharger le MP4

```bash
curl -L http://localhost:8080/v1/videos/<job_id>/download -o video.mp4
```

## 6. Lire le rapport de verification

```bash
curl http://localhost:8080/v1/videos/<job_id>/report
```

Le rapport contient les resultats `ffprobe`, `freezedetect` et les chemins de snapshots extraits.

## Arreter l'API

```bash
docker compose down
```

Pour supprimer aussi les volumes de jobs et la base locale :

```bash
docker compose down -v
```

Attention : `-v` supprime les artefacts et les metadonnees locales.
