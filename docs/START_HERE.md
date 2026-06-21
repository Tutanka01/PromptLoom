# Commencer avec PromptLoom

Cette page donne le modèle mental du projet et oriente vers le bon parcours. Tu
n'as pas besoin de comprendre Manim, Celery ou le TTS pour créer un premier job.

## Choisis ton parcours

### Je veux voir ce que produit PromptLoom

1. Regarde les exemples [français](../videos/examples/fran%C3%A7ais-exemple.mp4)
   et [espagnol](../videos/examples/espagnol-exemple.mp4).
2. Reviens lire le modèle mental ci-dessous.
3. Consulte [Première vidéo](FIRST_VIDEO.md) si tu veux lancer la plateforme.

### Je veux utiliser l'API

1. Suis [Première vidéo](FIRST_VIDEO.md).
2. Lis ensuite la [référence API](../apps/video-api/docs/api-reference.md).
3. Choisis tes moteurs dans le
   [guide d'exploitation](../apps/video-api/docs/operations.md).

### Je veux contribuer

1. Lis [`AGENTS.md`](../AGENTS.md), même si tu travailles manuellement.
2. Lis [`CONTRIBUTING.md`](../CONTRIBUTING.md).
3. Ouvre le [guide développeur](../apps/video-api/docs/developer-guide.md).

### Je veux déployer

1. Lis l'[architecture](../apps/video-api/docs/architecture.md).
2. Configure l'[exploitation](../apps/video-api/docs/operations.md).
3. Si le TTS doit être déporté, configure
   [`tts-server`](../apps/tts-server/README.md).

## Le modèle mental en 90 secondes

Une requête ne renvoie pas immédiatement un MP4. Elle crée un **job asynchrone** :

```text
POST /v1/videos
  -> réponse 202 avec job_id
  -> worker exécute le pipeline
  -> GET /v1/videos/<job_id> expose la progression
  -> /download apparaît quand le job est completed
```

Le pipeline possède quatre contrats importants :

1. **Blueprint** — ce que la vidéo doit enseigner, scène par scène.
2. **Narration et beats** — ce qui est dit et le moment où l'image évolue.
3. **Moteur de rendu** — Manim ou Remotion matérialise les scènes.
4. **Rapport de qualité** — ffprobe, gels détectés, snapshots et éventuelle
   revue visuelle déterminent si le résultat est livrable.

Le LLM propose et répare. Le worker garde le contrôle des schémas, des fichiers,
des commandes exécutées et des critères de livraison.

## Les composants sans jargon

| Composant | Responsabilité | Si le composant est absent |
| --- | --- | --- |
| `api` | Reçoit les requêtes et expose les résultats. | Aucun client ne peut créer ou consulter de job. |
| `worker` | Produit réellement les vidéos. | Les jobs restent `queued`. |
| Redis | Transporte les tâches vers le worker. | La file de jobs ne fonctionne pas. |
| Postgres | Conserve états et métadonnées. | L'API passe en état dégradé. |
| LLM | Écrit le blueprint et éventuellement les scènes. | Utilise `VIDEO_API_FAKE_LLM=1` pour un blueprint de test. |
| TTS | Transforme chaque narration en audio. | Le pipeline ne peut pas synchroniser ni assembler le MP4. |
| Manim/Remotion | Produit la vidéo silencieuse. | Le job termine en `failed_render`. |

## Choisir une première configuration

| Besoin | Configuration conseillée |
| --- | --- |
| Vérifier la mécanique sans endpoint LLM | `VIDEO_API_FAKE_LLM=1`, profil `draft`. |
| Premier essai réel en anglais ou français | LLM réel, `quality_profile=draft`, Kokoro automatique. |
| Vidéo technique finale | `technical` + `standard`, Manim ou Remotion. |
| Vidéo narrative avec sources | `editorial`, fournisseur Tavily/Exa configuré. |
| Motion design avancé | `cinematic`, Remotion, recherche disponible. |
| Plusieurs langues, même contenu | `languages: ["fr", "en", "es"]`. |
| TTS multilingue GPU | `moss-remote` + `apps/tts-server`. |

## Ce qu'il faut savoir avant le premier lancement

- Le premier build est lourd : le worker contient rendu, audio, Torch, Node et
  Chrome headless. Ne confonds pas temps de build et temps normal de l'API.
- `VIDEO_API_FAKE_LLM=1` supprime l'appel LLM, pas la synthèse vocale ni le rendu.
- Un job vidéo est long par nature. Suis `current_step`, `progress` et les logs
  du worker au lieu d'attendre sur la requête HTTP initiale.
- Les fichiers sont dans `/data/jobs/<job_id>/` à l'intérieur du volume Docker,
  pas dans `videos/`.
- `docker compose down` conserve les données. `docker compose down -v` les
  supprime.
- L'API est ouverte par défaut : configure `VIDEO_API_KEYS` avant exposition.

## Définition d'un onboarding réussi

Tu es prêt quand tu sais :

- obtenir `status=ok` sur `/healthz`;
- créer un job et conserver son `job_id`;
- distinguer `queued`, une étape active, `completed` et `failed_*`;
- télécharger le MP4 et lire son rapport;
- trouver les logs du worker;
- arrêter la stack sans supprimer involontairement les volumes.

La suite pratique est [Créer sa première vidéo](FIRST_VIDEO.md).

