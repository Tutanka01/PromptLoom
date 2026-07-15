# Documentation

La documentation est organisée autour du produit principal, `video-api`, puis
des composants optionnels et des références historiques.

## Parcours principal

1. [`START_HERE.md`](START_HERE.md) — orientation et modèle mental en 90 secondes.
2. [`FIRST_VIDEO.md`](FIRST_VIDEO.md) — tutoriel copiable jusqu'au MP4 final.
3. [`../README.md`](../README.md) — vision, exemples et démarrage condensé.
4. [`../apps/studio/README.md`](../apps/studio/README.md) — Studio, l'interface
   web de pilotage livrée avec la plateforme.
5. [`REPOSITORY_STRUCTURE.md`](REPOSITORY_STRUCTURE.md) — frontières entre les
   applications et statut des anciens dossiers Linux.
6. [`../apps/video-api/docs/quickstart.md`](../apps/video-api/docs/quickstart.md)
   — créer et suivre un premier job depuis un terminal.
7. [`../apps/video-api/docs/architecture.md`](../apps/video-api/docs/architecture.md)
   — services et cycle de vie d'un job.
8. [`../apps/video-api/docs/developer-guide.md`](../apps/video-api/docs/developer-guide.md)
   — travailler sur le produit.
9. [`../apps/video-api/docs/operations.md`](../apps/video-api/docs/operations.md)
   — configuration, déploiement et diagnostic.

Pour contribuer, lire aussi [`../CONTRIBUTING.md`](../CONTRIBUTING.md).

L'index complet de l'application se trouve dans
[`apps/video-api/docs`](../apps/video-api/docs/README.md).

## Service optionnel

[`apps/tts-server`](../apps/tts-server/README.md) déporte MOSS-TTS sur une
machine GPU dédiée. `video-api` fonctionne sans ce service avec ses autres
moteurs vocaux.

## Références historiques

Le dépôt vient d'un pipeline manuel de vidéos sur Linux. Ces documents restent
utiles pour maintenir les exemples et contrôler la qualité éditoriale :

- [`../PROCEDURE.md`](../PROCEDURE.md) — procédure manuelle complète;
- [`VIDEO_PRODUCTION_STANDARD.md`](VIDEO_PRODUCTION_STANDARD.md) — standard v2
  de synchronisation et de vérification;
- [`VOICE_AND_AUDIO.md`](VOICE_AND_AUDIO.md) — politique de voix historique;
- [`VIDEOS.md`](VIDEOS.md) — registre des productions suivies;
- [`boilerplate`](boilerplate/README.md) — squelette du pipeline manuel;
- [`videos`](videos/) — plans et scripts des exemples Linux.

Ces références ne sont pas le parcours de démarrage de la plateforme et les
jobs de l'API ne doivent pas y être écrits.

## Politique documentaire

- La documentation transverse vit à la racine ou dans `docs/`.
- La documentation spécifique à une application vit avec celle-ci sous
  `apps/<application>/docs/`.
- Les dossiers historiques `videos/...` ne contiennent que des sources de
  production et des MP4 sélectionnés, jamais de README opérationnel.
- Les plans et scripts des vidéos manuelles restent dans
  `docs/videos/<theme>/<slug>/`.
