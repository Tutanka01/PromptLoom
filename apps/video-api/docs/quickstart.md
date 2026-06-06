# Quickstart

Ce guide montre comment lancer l'API et creer un job video depuis un terminal.

## 1. Configurer l'environnement

Depuis la racine du depot :

```bash
cd apps/video-api
cp .env.example .env
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
