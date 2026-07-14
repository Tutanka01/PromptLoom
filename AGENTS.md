# AGENTS.md

Guide minimal pour les agents qui travaillent sur PromptLoom. Le but est de
donner le contexte stable et de router vers la bonne source sans charger toute
la documentation.

## Règle de lecture

Lis ce fichier une fois. Ensuite, ne lis que la ligne pertinente de la table de
routage. Ne charge pas `PROCEDURE.md` ni les documents historiques pour une
tâche `video-api` ordinaire.

## PromptLoom en bref

- Produit principal : `apps/video-api/`.
- Entrée du dépôt : `compose.yaml` à la racine.
- API asynchrone : FastAPI crée les jobs, Celery les exécute via Redis, Postgres
  conserve leur état.
- Pipeline : prompt → recherche optionnelle → blueprint validé → narration et
  scènes → TTS → Manim ou Remotion → ffmpeg → contrôles → MP4.
- Les jobs vivent dans `/data/jobs/<job_id>/`, jamais dans le dossier source
  `videos/`.
- `apps/tts-server/` est un service GPU MOSS-TTS optionnel.
- `apps/studio/` est le front-end web (React/Vite/Tailwind) de pilotage de l'API.
- Le contrat éditorial est actuellement optimisé pour les sujets STEM.
- `videos/examples/` contient la vitrine; `videos/linux-fondamentaux/` contient
  l'origine manuelle historique du projet.

Principe qualité central : la voix et l'image doivent expliquer la même chose
au même moment.

## Routage documentaire

| Tâche | Lire uniquement |
| --- | --- |
| Comprendre ou présenter le produit | `README.md`, puis `docs/START_HERE.md` si nécessaire |
| Organisation du monorepo | `docs/REPOSITORY_STRUCTURE.md` |
| Première utilisation de l'API | `docs/FIRST_VIDEO.md` |
| Endpoint, requête ou réponse HTTP | `apps/video-api/docs/api-reference.md`, puis `main.py` et `schemas.py` |
| Architecture, états ou cycle d'un job | `apps/video-api/docs/architecture.md` |
| Modifier le pipeline worker | `apps/video-api/docs/developer-guide.md`, puis le module concerné |
| Contrat ou normalisation LLM | `apps/video-api/docs/llm-contract.md`, `schemas.py`, `pipeline/llm.py` |
| Production éditoriale, recherche ou médias | `apps/video-api/docs/advanced-production.md` |
| Rendu Remotion | `apps/video-api/docs/remotion-engine.md`; ajouter `remotion-catalog.md` ou `remotion-skill.md` seulement si nécessaire |
| Génération Manim | `apps/video-api/docs/manim-generation-guidelines.md`; `manim-skill.md` seulement pour l'authoring de scènes |
| Configuration, Docker, logs ou rétention | `apps/video-api/docs/operations.md` |
| Service GPU TTS | `apps/tts-server/README.md` |
| Front-end web de pilotage | `apps/studio/README.md` |
| Contribution générale | `CONTRIBUTING.md` |
| Vidéo manuelle historique | `PROCEDURE.md` et `docs/VIDEO_PRODUCTION_STANDARD.md` |

## Carte du code

```text
apps/video-api/src/video_api/
  main.py                 HTTP, auth, création/status/download/report
  tasks.py                tâches Celery et fan-out multilingue
  schemas.py              contrats Pydantic publics et LLM
  config.py               variables d'environnement et profils qualité
  voices.py               catalogue de voix TTS et sélection par requête
  db.py / models.py       persistance, rétention, jobs périmés
  pipeline/
    production.py         orchestration et classification des échecs
    llm.py                client OpenAI-compatible et normalisation
    materialize.py        fichiers et scènes Manim
    remotion_materialize.py / remotion_scene_coder.py
    validate.py           garde-fous des sources générées
    voice.py              sélection du TTS et cache par segment
    research.py / assets.py / editorial.py
    verify.py             ffprobe, freezedetect, snapshots

apps/video-api/remotion/  catalogue et runtime React/Remotion
apps/tts-server/src/      API, moteur, cache et file MOSS-TTS
```

## Règles non négociables

### Portée et données

- Préserve les changements utilisateur et les fichiers non suivis.
- Pas de `git reset --hard`, nettoyage massif ou suppression sans demande
  explicite.
- Consulte `git status --short` avant de terminer.
- N'écris jamais un job API dans `videos/`; utilise le volume `/data/jobs`.
- Les secrets restent dans `.env`, jamais dans le code, les logs ou Git.

### Contrats produit

- Le LLM produit d'abord un blueprint structuré validé par Pydantic.
- Le scene-coder peut produire du code Manim/TSX uniquement via les validations,
  smoke checks et fallbacks existants. Ne contourne pas ces garde-fous.
- Une langue secondaire d'un batch traduit le blueprint maître validé; elle ne
  régénère pas un contenu différent.
- Une erreur TTS distante fait échouer clairement le job. Aucun fallback de voix
  silencieux.
- Préserve les caches audio par segment; ne régénère pas les voix inchangées.
- Les noms historiques `segments_en.json` et `audio/en/` restent utilisés pour
  compatibilité, même lorsque la narration n'est pas anglaise.

### Documentation

- Documentation transverse : racine ou `docs/`.
- Documentation d'une application : `apps/<app>/docs/`.
- Pas de README ou de notes opérationnelles dans une production sous `videos/`.
- Si un comportement public, une variable ou une commande change, mets à jour
  la documentation correspondante dans la même modification.
- Pour un modèle, une bibliothèque ou une API susceptible d'avoir changé,
  vérifier la documentation officielle actuelle plutôt que se fier à la mémoire.

## Pièges techniques à ne pas redécouvrir

- Manim Docker 0.18.1 : utiliser `self.renderer.time`, pas `self.time` au début
  d'une scène.
- Manim rend sous `media/videos/<nom_du_module>/...`; le module inclut le suffixe
  de langue.
- Les polices macOS ne sont pas présentes dans Linux; utiliser les polices déjà
  définies par le projet.
- Pour diagnostiquer un rendu, lire le fichier de log complet du job, pas
  seulement `error.json` ou la dernière ligne affichée.
- La durée audio réelle pilote la scène. Ne corrige pas une synchro avec des
  attentes arbitraires ou un long écran figé.
- Le matérialiseur Manim copie encore `generate_voice_en.py` depuis la vidéo
  syscall historique. Ne déplace pas cette référence sans extraire et tester la
  ressource dans `video-api`.
- L'API est ouverte si `VIDEO_API_KEYS` est vide. Ne recommande pas une exposition
  réseau sans authentification.
- `docker compose down -v` supprime les jobs et la base locale.

## Méthode de travail et validations

Fais toutes les modifications cohérentes avant de tester. Lance une seule passe
finale proportionnée au risque; ne rebuild pas Docker après chaque fichier.

Contrôles légers depuis la racine :

```bash
python3 -m py_compile $(find apps/video-api/src apps/video-api/tests -name '*.py' -print)
docker compose config --quiet
git diff --check
git status --short
```

Tests `video-api` si le code Python ou le comportement change :

```bash
apps/video-api/.venv/bin/pytest -q apps/video-api/tests   # si le venv local existe
# sinon, ou si Docker est précisément dans la portée :
docker compose run --rm test
```

Le test Docker peut construire une image lourde. Pour une modification purement
documentaire, valider les liens, Compose et le diff suffit.

Si le rendu est touché, ajouter un smoke render dans Docker. Si seul
`tts-server` est touché :

```bash
python3 -m py_compile $(find apps/tts-server/src apps/tts-server/tests -name '*.py' -print)
docker compose -f apps/tts-server/compose.yaml config --quiet
apps/tts-server/.venv/bin/pytest -q apps/tts-server/tests  # si disponible
# sinon : docker compose -f apps/tts-server/compose.yaml run --rm test
```

## Pipeline manuel historique

Cette section ne s'applique qu'à une demande explicite sur une vidéo suivie dans
`videos/linux-fondamentaux/` ou à une nouvelle production manuelle.

- Lire `PROCEDURE.md` et `docs/VIDEO_PRODUCTION_STANDARD.md` avant d'agir.
- Garder Chatterbox principal non-turbo sauf accord explicite pour changer de
  voix ou de modèle.
- Synchroniser avec `audio/en/durations.json` et `beats_en.json`.
- Rendre d'abord en basse qualité, inspecter ffprobe/freezedetect/snapshots, puis
  rendre et revérifier le final.
- Ne jamais déclarer une vidéo terminée sans audio, vidéo silencieuse, MP4 final,
  contrôles techniques et inspection de plusieurs frames.

## Quand demander confirmation

Demande seulement si le choix change matériellement le résultat ou l'autorité :

- langue, voix ou modèle TTS;
- forte réduction de durée ou suppression d'une scène;
- action destructive;
- nouveau service externe, secret ou dépense;
- changement de portée au-delà de la demande.

Sinon, avance avec les conventions existantes.

## Définition de terminé

- Changement demandé réellement implémenté, sans refactor hors sujet.
- Contrats et documentation cohérents.
- Validation finale adaptée exécutée une fois; résultats rapportés honnêtement.
- Aucun échec masqué et aucune affirmation de propreté si le worktree est sale.
- Pour un job API livré : statut terminal correct, rapport disponible et MP4
  téléchargeable.
- Pour une vidéo manuelle : appliquer la définition complète de
  `PROCEDURE.md`.
