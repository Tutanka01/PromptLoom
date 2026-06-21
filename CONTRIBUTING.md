# Contribuer à PromptLoom

## Avant de commencer

Lis :

1. [`AGENTS.md`](AGENTS.md) — règles du dépôt;
2. [`docs/REPOSITORY_STRUCTURE.md`](docs/REPOSITORY_STRUCTURE.md) — frontières;
3. [`apps/video-api/docs/developer-guide.md`](apps/video-api/docs/developer-guide.md)
   — architecture du code et points d'extension.

Pour le pipeline manuel historique uniquement, ajoute `PROCEDURE.md` et
`docs/VIDEO_PRODUCTION_STANDARD.md`.

## Choisir le bon emplacement

- Produit principal, API, worker ou rendu : `apps/video-api/`.
- Service TTS GPU : `apps/tts-server/`.
- Documentation transverse : racine ou `docs/`.
- Documentation propre à une application : `apps/<app>/docs/`.
- MP4 de démonstration sélectionné : `videos/examples/`.
- Ne jamais écrire un job API dans le dossier source `videos/`.

## Boucle de travail

1. Comprends le contrat concerné et ses tests.
2. Modifie le minimum cohérent.
3. Mets à jour la documentation dans la même modification.
4. Termine l'ensemble des changements avant de lancer les validations lourdes.
5. Exécute une seule passe finale adaptée au risque.
6. Consulte `git status --short` et distingue tes changements des modifications
   utilisateur déjà présentes.

## Validation

Contrôles statiques rapides :

```bash
python3 -m py_compile $(find apps/video-api/src apps/video-api/tests -name '*.py' -print)
docker compose config --quiet
git diff --check
```

Suite principale, à lancer une fois à la fin lorsque le code est touché :

```bash
docker compose run --rm test
```

Le premier lancement peut construire l'image lourde. Un changement purement
documentaire ne justifie pas ce rebuild; vérifie alors les liens, Compose et le
diff.

Pour `tts-server` :

```bash
python3 -m py_compile $(find apps/tts-server/src apps/tts-server/tests -name '*.py' -print)
docker compose -f apps/tts-server/compose.yaml config --quiet
docker compose -f apps/tts-server/compose.yaml run --rm test
```

## Critères de qualité

- Le comportement public est documenté.
- Les valeurs par défaut restent cohérentes entre code, Compose et `.env.example`.
- Aucun secret, cache, environnement virtuel ou artefact de job n'est ajouté.
- Les erreurs restent diagnostiquables dans les logs du job.
- Une vidéo n'est pas dite terminée sans ses contrôles techniques et visuels.
