# API Reference

Base URL locale :

```text
http://localhost:8080
```

## Authentification (optionnelle)

Si `VIDEO_API_KEYS` est defini (liste de cles separees par des virgules), tous
les endpoints `/v1/*` exigent l'en-tete `X-API-Key`. Sans cette variable,
l'API reste ouverte (comportement historique). `/healthz` reste toujours
ouvert pour les probes.

## `GET /healthz`

Verifie l'API ET ses dependances (ping Postgres + Redis).

```bash
curl http://localhost:8080/healthz
```

Reponse :

```json
{"status":"ok","checks":{"database":"ok","redis":"ok"}}
```

HTTP `503` avec `"status":"degraded"` si une dependance ne repond pas.

## `POST /v1/videos`

Cree un job de generation video.

### Requete minimale

```bash
curl -X POST http://localhost:8080/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Make a short video explaining derivatives intuitively","theme":"math"}'
```

Exemple multilingue :

```bash
curl -X POST http://localhost:8080/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Explique les appels systeme Linux","theme":"cs","language":"fr"}'
```

### Corps JSON

```json
{
  "prompt": "Explique intuitivement ce qu est un appel systeme Linux",
  "theme": "linux-fondamentaux",
  "language": "it",
  "target_duration_seconds": 240,
  "quality_profile": "standard",
  "callback_url": null
}
```

Champs :

- `prompt` obligatoire, entre 10 et 4000 caracteres. Il peut etre ecrit dans
  n'importe quelle langue. Ce n'est pas lui qui choisit la langue finale de la
  video ; c'est le champ `language`.
- `theme` optionnel, aide a classer le job et a nommer les artefacts. Exemples :
  `math`, `cs`, `linux-fondamentaux`, `physics`.
- `language` optionnel, defaut `en`. C'est la langue de sortie : narration TTS,
  texte visible, labels et beats. Codes supportes par MOSS-TTS v1.5 :
  `zh`, `yue`, `en`, `ar`, `cs`, `da`, `de`, `nl`, `es`, `fr`, `fi`, `el`,
  `he`, `hi`, `hu`, `it`, `ja`, `ko`, `mk`, `ms`, `fa`, `pl`, `pt`, `ro`,
  `ru`, `sw`, `sv`, `tl`, `th`, `tr`, `vi`. Pour les langues europeennes, cela
  couvre notamment anglais, francais, espagnol, italien, portugais, allemand,
  neerlandais, roumain, polonais, tcheque, danois, suedois, finnois, grec,
  hongrois, macedonien, russe et turc. La narration
  et les textes visibles sont generes dans cette langue, meme si le prompt est dans
  une autre langue. Les tags regionaux comme `fr-FR` ou `it-IT` sont normalises en
  `fr` et `it`.
- `target_duration_seconds` optionnel, entre 45 et 900 secondes. C'est une cible
  pedagogique pour le LLM, pas une duree garantie a l'image pres : le pipeline
  ecrit assez de narration pour s'approcher de cette duree, puis la duree reelle
  vient des WAV generes et de `audio/en/durations.json`. S'il est absent, l'API
  vise 240 secondes et rejette les rendus anormalement courts.
- `quality_profile` optionnel, defaut `standard` :
  `draft` = iteration rapide, force Kokoro, rendu demi-resolution, pas de revue
  visuelle. A utiliser surtout pour EN/FR ; pour italien, espagnol, roumain, etc.,
  prefere `standard` avec `VIDEO_API_VOICE_ENGINE=moss`.
  `standard` = profil de production avec les reglages voix/rendu configures.
  `high` = `standard` + revue visuelle forcee si `VIDEO_API_VISION_MODEL` est defini
  + controle de gel fatal.
  `final` = ancien nom, alias de `standard`.
- `callback_url` : si fourni, l'API POSTe un webhook JSON a la fin du job
  (completed / failed_* / cancelled), avec 3 tentatives et signature HMAC-SHA256
  dans `X-Video-API-Signature` quand `VIDEO_API_WEBHOOK_SECRET` est defini.

Exemple conseille pour une video italienne avec un prompt francais :

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

## `GET /v1/videos`

Liste les jobs (tries du plus recent au plus ancien).

```bash
curl 'http://localhost:8080/v1/videos?status=completed&limit=20&offset=0'
```

## `DELETE /v1/videos/{job_id}`

Annule un job en file ou en cours. Le worker s'arrete a la prochaine frontiere
d'etape (une sous-commande longue finit son etape en cours). `409` si le job
est deja terminal.

```bash
curl -X DELETE http://localhost:8080/v1/videos/<job_id>
```

## `GET /v1/videos/{job_id}/artifacts/{chemin}`

Sert n'importe quel fichier du workspace du job (protection path-traversal) :
`blueprint.json`, `logs/render-low.log`, `reports/final/freeze.json`,
`reports/final/snapshots/check_01_0010.png`, ...

```bash
curl http://localhost:8080/v1/videos/<job_id>/artifacts/blueprint.json
curl http://localhost:8080/v1/videos/<job_id>/artifacts/logs/render-final.log
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
