# Créer sa première vidéo

Objectif : lancer PromptLoom, créer une vidéo courte, suivre le job puis
télécharger le MP4 et son rapport. Toutes les commandes partent de la racine du
dépôt.

## 1. Préparer l'environnement

```bash
cp apps/video-api/.env.example .env
```

Pour une vraie vidéo, configure un endpoint compatible OpenAI :

```text
OPENAI_BASE_URL=http://host.docker.internal:8000/v1
OPENAI_API_KEY=...
OPENAI_MODEL=...
VIDEO_API_FAKE_LLM=0
```

Pour valider le pipeline sans LLM :

```text
VIDEO_API_FAKE_LLM=1
```

Ce dernier mode produit un contenu déterministe. Il continue à lancer le TTS,
le rendu et les contrôles.

## 2. Faire le diagnostic préalable

```bash
make doctor
```

Le diagnostic vérifie Docker, la version de Compose et la résolution du fichier
`compose.yaml`. Il ne construit aucune image.

## 3. Démarrer la plateforme

```bash
make start
```

Le premier build peut être long. Ensuite :

```bash
make status
make health
```

Réponse saine :

```json
{"status":"ok","checks":{"database":"ok","redis":"ok"}}
```

Si l'API démarre avant que Postgres soit prêt, attends quelques secondes puis
relance `make health`.

## 4. Créer un job court

Le profil `draft` est adapté à une première boucle. Il privilégie la vitesse et
force Kokoro pour l'anglais ou le français.

```bash
RESPONSE=$(curl -sS -X POST http://localhost:8080/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Explain visually how a neural network learns from an error signal",
    "theme": "computer-science",
    "language": "en",
    "target_duration_seconds": 60,
    "quality_profile": "draft",
    "production_mode": "technical"
  }')

echo "$RESPONSE"
JOB_ID=$(printf '%s' "$RESPONSE" | python3 -c 'import json,sys; print(json.load(sys.stdin)["job_id"])')
```

Si `VIDEO_API_KEYS` est configuré, ajoute à chaque requête :

```text
-H 'X-API-Key: <ta-cle>'
```

## 5. Suivre ce qui se passe

Consulter l'état :

```bash
curl "http://localhost:8080/v1/videos/$JOB_ID"
```

Suivre les logs utiles :

```bash
make logs
```

États à connaître :

- `queued` : le job attend le worker;
- `planning`, `voice_generation`, `render_*`, `verify_*` : travail en cours;
- `completed` : MP4 disponible;
- `failed_generation` : recherche, LLM, schéma ou matérialisation;
- `failed_render` : Manim, Remotion, voix ou commande de production;
- `failed_quality` : contrôle technique ou qualité bloquante;
- `failed_visual_review` : revue visuelle insuffisante;
- `failed_stale` : job abandonné depuis trop longtemps.

Les logs complets d'une commande sont conservés dans le workspace du job; ne
diagnostique pas un rendu uniquement à partir de la dernière ligne affichée.

## 6. Télécharger et vérifier

Quand le job est `completed` :

```bash
curl -L "http://localhost:8080/v1/videos/$JOB_ID/download" -o promptloom-first-video.mp4
curl "http://localhost:8080/v1/videos/$JOB_ID/report"
```

Le rapport décrit les pistes audio/vidéo, la résolution, le framerate, les gels
détectés et les snapshots. Un MP4 livré avec un avertissement de gel mérite une
inspection humaine.

## 7. Essayer les capacités importantes

### Sortie dans une autre langue

Le prompt peut rester en français :

```json
{
  "prompt": "Explique comment une cellule transforme le glucose en énergie",
  "theme": "biology",
  "language": "es",
  "target_duration_seconds": 90,
  "quality_profile": "standard"
}
```

### Même vidéo dans trois langues

```json
{
  "prompt": "Explique le fonctionnement d une table de hachage",
  "theme": "computer-science",
  "languages": ["fr", "en", "es"],
  "target_duration_seconds": 90,
  "quality_profile": "standard"
}
```

La première langue génère le blueprint maître. Les autres jobs traduisent ce
même contenu après réussite de la primaire.

### Mode éditorial

Configure Tavily ou Exa dans `.env`, puis utilise :

```json
{
  "prompt": "Explain how CRISPR editing works and where its limits are",
  "theme": "biology",
  "language": "en",
  "production_mode": "editorial",
  "research": {"enabled": true, "required": true, "max_sources": 8},
  "visuals": {"strategy": "hybrid", "allow_stock": false, "max_assets": 0},
  "captions": "keywords"
}
```

## Diagnostic express

| Symptôme | Cause probable | Action |
| --- | --- | --- |
| `/healthz` retourne `503` | Postgres ou Redis indisponible. | `docker compose ps`, puis logs du service concerné. |
| Le job reste `queued` | Worker absent ou déconnecté de Redis. | `docker compose ps worker` et `docker compose logs worker`. |
| `failed_generation` | LLM inaccessible, JSON invalide ou recherche requise non configurée. | Vérifie `.env`, puis le log LLM/recherche du job. |
| `failed_render` | Erreur Manim/Remotion/TTS ou timeout. | Lis le fichier complet `render-*.log` ou `voice.log`. |
| `failed_quality` | Piste, durée, résolution ou gate qualité invalide. | Consulte `/report` et `reports/`. |
| Le téléchargement retourne `404` | Job incomplet ou artefacts expirés. | Vérifie le statut et `VIDEO_API_JOB_TTL_DAYS`. |
| La voix est lente | Chatterbox sur CPU. | Utilise `draft`, Kokoro, OpenAI TTS ou `moss-remote`. |

## Arrêter proprement

```bash
make down
```

Cette commande conserve les volumes. Pour effacer volontairement tous les jobs
et la base locale :

```bash
docker compose down -v
```

Prochaine lecture : [Référence API](../apps/video-api/docs/api-reference.md).

