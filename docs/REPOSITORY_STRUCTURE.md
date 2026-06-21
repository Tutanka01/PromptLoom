# Organisation du dépôt

## Décision

`apps/video-api` est le produit principal. La racine sert de façade au monorepo :
elle présente la plateforme, fournit le point d'entrée Docker Compose et agrège
les commandes de développement.

Cette organisation garde des frontières explicites entre les composants sans
déplacer le code mature ni dupliquer les fichiers Compose :

```text
compose.yaml
  -> apps/video-api/compose.yaml
       -> api + worker + redis + postgres

apps/tts-server/
  -> accélérateur TTS GPU optionnel

videos/ + docs/videos/
  -> productions Linux historiques et références qualité

videos/examples/
  -> MP4 de démonstration visibles depuis le README
```

## Responsabilités

### `apps/video-api/`

Contient tout ce qui est nécessaire au produit principal : contrat HTTP,
orchestration des jobs, génération LLM, moteurs Manim et Remotion, client TTS,
assemblage, vérification, tests et documentation opérationnelle.

Les nouveaux développements produit doivent aller ici, sauf s'ils constituent
clairement un service déployable séparément.

### `apps/tts-server/`

Service optionnel et indépendant. Il expose MOSS-TTS sur une machine GPU et ne
doit pas devenir une dépendance obligatoire de l'API.

### `docs/`

Documentation transverse. Les documents consacrés au pipeline manuel et les
plans des vidéos Linux sont des références historiques, pas l'entrée principale
de la plateforme.

### `videos/`

Exemples de production qui ont servi à concevoir le pipeline. L'API n'y écrit
pas ses jobs; elle utilise `/data/jobs/<job_id>/` dans un volume Docker.

## Règles d'évolution

- La racine reste légère : présentation, orchestration et documentation
  transverse uniquement.
- Le code exécutable appartient à une application sous `apps/`.
- Un nouveau service autonome peut être ajouté sous `apps/<service>/` avec ses
  propres tests et son propre fichier Compose.
- Les artefacts de jobs, caches, environnements virtuels et `node_modules` ne
  sont pas versionnés.
- Les exemples Linux ne doivent plus fournir de dépendance conceptuelle au
  produit. Les dépendances techniques historiques restantes doivent être
  extraites progressivement vers `apps/video-api`.

## Dette structurelle connue

Le matérialiseur copie encore `generate_voice_en.py` depuis la vidéo syscall de
référence. Ce lien est stable et testé, mais il reste un couplage historique. La
bonne évolution consiste à transformer ce script en ressource versionnée dans
`apps/video-api`, avec ses propres tests, puis à laisser les vidéos historiques
en lecture seule.
