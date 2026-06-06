# API Reference

Base URL locale :

```text
http://localhost:8080
```

## `GET /healthz`

Verifie que l'API repond.

```bash
curl http://localhost:8080/healthz
```

Reponse :

```json
{"status":"ok"}
```

## `POST /v1/videos`

Cree un job de generation video.

### Requete minimale

```bash
curl -X POST http://localhost:8080/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Make a short video explaining derivatives intuitively","theme":"math"}'
```

### Corps JSON

```json
{
  "prompt": "Make a short video explaining derivatives intuitively",
  "theme": "math",
  "language": "en",
  "target_duration_seconds": 240,
  "quality_profile": "final",
  "callback_url": null
}
```

Champs :

- `prompt` obligatoire, entre 10 et 4000 caracteres.
- `theme` optionnel, aide a classer le job.
- `language` vaut actuellement `en`.
- `target_duration_seconds` optionnel, entre 45 et 900 secondes. S'il est absent, l'API vise 240 secondes et verifie que le rendu final n'est pas une video courte.
- `quality_profile` vaut actuellement `final`.
- `callback_url` est reserve pour une evolution future.

### Reponse

```json
{
  "job_id": "c52681fd-6cd3-4538-9a2f-c5a199186585",
  "status_url": "/v1/videos/c52681fd-6cd3-4538-9a2f-c5a199186585",
  "download_url": null
}
```

HTTP `202 Accepted` signifie que le job est accepte et execute en asynchrone.

## `GET /v1/videos/{job_id}`

Retourne l'etat d'un job.

```bash
curl http://localhost:8080/v1/videos/<job_id>
```

Reponse typique :

```json
{
  "job_id": "<job_id>",
  "status": "render_final",
  "progress": 78,
  "current_step": "render_final",
  "error_message": null,
  "download_url": null,
  "report_url": null
}
```

Quand la video est prete :

```json
{
  "job_id": "<job_id>",
  "status": "completed",
  "progress": 100,
  "current_step": "completed",
  "error_message": null,
  "download_url": "/v1/videos/<job_id>/download",
  "report_url": "/v1/videos/<job_id>/report"
}
```

## `GET /v1/videos/{job_id}/download`

Telecharge le MP4 final.

```bash
curl -L http://localhost:8080/v1/videos/<job_id>/download -o video.mp4
```

Reponses possibles :

- `200 OK`: MP4 disponible.
- `404 Not Found`: job ou fichier introuvable.
- `409 Conflict`: la video n'est pas encore prete.

## `GET /v1/videos/{job_id}/report`

Telecharge le rapport JSON de verification.

```bash
curl http://localhost:8080/v1/videos/<job_id>/report
```

Le rapport peut contenir :

- duree ;
- infos `ffprobe` ;
- stream video ;
- stream audio ;
- resume `freezedetect` ;
- chemins de snapshots.

## Polling recommande cote client

Exemple shell :

```bash
JOB_ID="<job_id>"

while true; do
  STATUS_JSON="$(curl -fsS "http://localhost:8080/v1/videos/${JOB_ID}")"
  echo "${STATUS_JSON}"

  STATUS="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])' <<< "${STATUS_JSON}")"

  if [ "${STATUS}" = "completed" ]; then
    curl -L "http://localhost:8080/v1/videos/${JOB_ID}/download" -o video.mp4
    break
  fi

  case "${STATUS}" in
    failed_generation|failed_render|failed_quality)
      echo "Job failed"
      exit 1
      ;;
  esac

  sleep 10
done
```

## Statuts d'erreur

- `failed_generation`: erreur de blueprint, validation ou generation des sources.
- `failed_render`: erreur pendant voix, rendu Manim ou assemblage.
- `failed_quality`: la video a ete produite mais les controles finaux ont echoue.

Dans tous les cas, consulte `report_url` si disponible.
