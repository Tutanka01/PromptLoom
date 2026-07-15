# Créer sa première vidéo

Objectif : lancer PromptLoom, créer une vidéo courte, suivre le job puis
récupérer le MP4 et son rapport. Toutes les commandes partent de la racine du
dépôt.

## Deux façons de piloter la plateforme

| | Studio (interface web) | API HTTP |
| --- | --- | --- |
| Pour qui | Première vidéo, usage quotidien, démonstration | Intégration, script, automatisation |
| Ce que tu obtiens | Formulaire construit depuis les capacités réelles du serveur, suivi en direct, lecteur vidéo, rapport et artefacts | Contrôle total du contrat JSON |
| Adresse | `http://localhost:3000` | `http://localhost:8080` |

Le Studio est démarré par la même commande que le reste de la stack : tu n'as
rien à installer en plus, et **`curl` n'est plus obligatoire**. Ce tutoriel
donne les deux parcours à l'étape 5 ; prends le Studio si tu découvres le
projet.

## 1. Préparer l'environnement

```bash
cp apps/video-api/.env.example .env
```

### Le LLM

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

### Le moteur audio — le choix qui change le plus ton expérience

La voix est synthétisée à chaque job, et la durée réelle des WAV pilote le
montage. Le moteur est un **choix de déploiement** (`.env`), contrairement à la
*voix*, qui se choisit par requête. C'est le réglage le plus structurant du
`.env` : il décide des langues disponibles et du temps d'attente de chaque job.

| `VIDEO_API_VOICE_ENGINE` | Langues | Coût / vitesse | Voix sélectionnable |
| --- | --- | --- | --- |
| `chatterbox` *(défaut du fichier d'exemple)* | **anglais uniquement** | Lent sur CPU | Non, timbre unique |
| `kokoro` | `en`, `fr` | Local, ~5× temps réel sur CPU | 8 voix cataloguées |
| `moss` | Toutes les langues acceptées par l'API | Local, lourd — confortable seulement avec un GPU | Oui, via la banque de voix (WAV de référence) |
| `moss-remote` | Toutes | Déporté sur [`apps/tts-server`](../apps/tts-server/README.md), modèle gardé en VRAM | Oui, via la banque de voix |
| `openai` | Selon ton serveur | Appel réseau, rapide, facturé | Voix exposées par le serveur |

Recommandations :

- **Tu démarres, tu produis en anglais ou en français** → `kokoro`. C'est le
  meilleur rapport qualité/temps sans GPU, et le profil `draft` l'utilise de
  toute façon.

  ```text
  VIDEO_API_VOICE_ENGINE=kokoro
  VIDEO_API_VOICE_LANGUAGE=en      # en | fr
  VIDEO_API_KOKORO_VOICE=af_bella  # ff_siwis pour le français
  ```

- **Tu veux une autre langue** → `chatterbox` et `kokoro` ne suffisent pas.
  Prends `moss` (avec GPU) ou `openai` (sans GPU). Attention : `quality_profile=draft`
  force Kokoro et retombe donc sur EN/FR — utilise `standard` pour ces langues.
- **Tu as une machine GPU séparée** → `moss-remote`, la meilleure combinaison
  qualité multilingue / temps d'attente. Voir [`apps/tts-server`](../apps/tts-server/README.md).
- **Tu gardes `chatterbox`** → uniquement pour de l'anglais dont tu veux le
  timbre historique du projet, en acceptant l'attente sur CPU.

Une erreur TTS fait échouer le job explicitement : il n'y a jamais de bascule
silencieuse vers une autre voix.

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

Cette commande démarre l'API, le worker, Redis, Postgres **et le Studio**. Le
premier build peut être long. Ensuite :

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

Le Studio est alors sur <http://localhost:3000> (change le port avec
`STUDIO_PORT`). Il sert le front-end et relaie `/v1` vers l'API : même origine,
donc pas de CORS à configurer.

## 4. Créer un job court

Le profil `draft` est adapté à une première boucle. Il privilégie la vitesse et
force Kokoro pour l'anglais ou le français.

### Parcours A — depuis le Studio (recommandé)

1. Ouvre <http://localhost:3000>.
2. Si l'API exige une clé (`VIDEO_API_KEYS` défini), colle-la dans **Réglages**
   en haut à droite. Elle est conservée dans le navigateur et envoyée en
   en-tête `X-API-Key`.
3. Va dans **Créer** et remplis l'essentiel : sujet, langue, voix, durée,
   qualité. Choisis `draft` et 60 secondes pour cette première boucle.
4. Lance. Le Studio bascule sur la page du job.

Le formulaire est construit à partir de `GET /v1/capabilities`, c'est-à-dire de
l'état réel de ton déploiement : tu ne verras que les langues que ton moteur TTS
sait parler, la recherche et les médias stock sont grisés sans fournisseur
configuré, et le profil « Élevé » est désactivé sans modèle vision. Les options
fines vivent dans **Avancé** ; un récapitulatif au-dessus du bouton indique ce
qui sera réellement produit.

C'est le moyen le plus simple de découvrir les capacités du serveur : si une
option est absente du formulaire, c'est que le `.env` ne la permet pas.

### Parcours B — depuis l'API

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

Pour connaître les voix disponibles avant de choisir le champ `voice` :

```bash
curl http://localhost:8080/v1/voices
```

## 5. Suivre ce qui se passe

Dans le Studio, la page du job affiche la progression étape par étape et
s'arrête d'elle-même quand le job atteint un état terminal. Le tableau de bord
liste tous les jobs.

En ligne de commande :

```bash
curl "http://localhost:8080/v1/videos/$JOB_ID"
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

## 6. Récupérer et vérifier

Dans le Studio, la page du job donne le lecteur vidéo, l'onglet **Rapport** et
l'onglet **Artefacts** (MP4, sous-titres, snapshots), téléchargeables même
lorsque l'API exige une clé.

En ligne de commande, quand le job est `completed` :

```bash
curl -L "http://localhost:8080/v1/videos/$JOB_ID/download" -o promptloom-first-video.mp4
curl "http://localhost:8080/v1/videos/$JOB_ID/report"
```

Le rapport décrit les pistes audio/vidéo, la résolution, le framerate, les gels
détectés et les snapshots. Un MP4 livré avec un avertissement de gel mérite une
inspection humaine.

## 7. Essayer les capacités importantes

Tout ce qui suit est disponible dans le formulaire du Studio (section
**Avancé** et onglet **Batch** pour le multilingue). Les payloads ci-dessous
sont l'équivalent API.

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

Rappel : l'espagnol demande un moteur multilingue (`moss`, `moss-remote` ou
`openai`), et `draft` n'est pas utilisable ici.

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
même contenu après réussite de la primaire. Le Studio suit le batch complet.

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

Sans fournisseur configuré, la recherche apparaît grisée dans le Studio et une
demande `required: true` fait échouer le job côté API.

## Diagnostic express

| Symptôme | Cause probable | Action |
| --- | --- | --- |
| Le Studio affiche une erreur de connexion | API arrêtée ou clé absente. | `make health`, puis renseigne la clé dans **Réglages**. |
| La langue voulue n'apparaît pas dans le formulaire | Le moteur TTS configuré ne la parle pas. | Passe à `moss`, `moss-remote` ou `openai` (voir étape 1). |
| Le profil « Élevé » est désactivé | Aucun modèle vision configuré. | Configure la revue visuelle ou reste en `standard`. |
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

Prochaine lecture : [Studio](../apps/studio/README.md) pour l'interface, ou
[Référence API](../apps/video-api/docs/api-reference.md) pour intégrer la
plateforme.
