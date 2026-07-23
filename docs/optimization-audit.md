# Audit d’optimisation du pipeline de génération vidéo

**Projet :** PromptLoom

**Date de l’audit :** 23 juillet 2026

**Révision analysée :** `d70b0a674d5d` (`main`)

**Périmètre :** `apps/video-api`, moteur Remotion et service `apps/tts-server`

**Nature de l’intervention :** analyse en lecture seule ; aucun fichier existant ni comportement du produit n’a été modifié.

## Résumé exécutif

PromptLoom possède déjà plusieurs fondations saines : blueprint validé par Pydantic, parallélisme des appels LLM par scène, limitation des smoke renders, réutilisation audio au sein d’un job, cache inter-jobs côté MOSS-TTS distant, concaténation vidéo sans réencodage et contrôles finaux complets. Le potentiel principal n’est donc pas dans des micro-optimisations de Python, Redis ou Postgres. Il se trouve dans quatre zones du chemin critique :

1. le TTS local par défaut recharge Chatterbox à chaque job et l’exécute sur CPU sous Linux ;
2. le rendu Manim final regroupe toutes les scènes dans une commande sans parallélisme explicite par scène ;
3. le scene-coder/smoke et le TTS sont indépendants mais exécutés l’un après l’autre ;
4. une réparation invalide ou efface une grande partie des artefacts pourtant inchangés.

L’absence de rapports de jobs réels dans le dépôt et dans `/data/jobs` empêche de présenter des gains mesurés. Toutes les fourchettes ci-dessous sont donc des **estimations de modèle de chemin critique**, à confirmer sur le matériel cible. Trois formules rendent les hypothèses explicites :

```text
gain d'un chevauchement = min(T_branche_A, T_branche_B) / T_total
gain moyen d'un cache = taux_de_hit × part_de_l'étape × fraction_de_coût_évitée
gain d'une étape parallélisée = part_de_l'étape × (1 - 1 / accélération_observée)
```

### Top 5 par ROI

Le classement utilise un score ordinal, et non une fausse précision financière :

- **gain `G`** : 1 = < 5 %, 2 = 5–10 %, 3 = 10–20 %, 4 = 20–35 %, 5 = > 35 % sur le chemin éligible ;
- **facilité `F`** : 1 = refonte, 2 = difficile, 3 = moyenne, 4 = faible, 5 = configuration ;
- **risque `R`** : 1 = faible, 1,25 = faible à moyen, 2 = moyen, 3 = élevé ;
- **score ROI** : `G × F / R`.

| Rang | Optimisation | Gain bout en bout estimé | G | F | R | Score ROI | Pourquoi elle est prioritaire |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | **TTS GPU persistant avec exactement le même modèle, la même voix et les mêmes paramètres**, puis cache exact et batch lorsque le moteur le permet | 15–45 % ; jusqu’à 55 % si le TTS domine réellement | 5 | 3 | 1,25 | 12,0 | Supprime à la fois le rechargement du modèle et le chemin CPU actuel, sans exiger un changement de voix. |
| 2 | **Serving LLM réglé par benchmark : continuous batching, concurrence par scène et cache de préfixe exact** | 5–15 % typique ; 1–8 % pour le cache de préfixe seul | 3 | 4 | 1,25 | 9,6 | Les longs préfixes répétés rendent le gain accessible sans réduire la narration ni changer le modèle cible. |
| 3 | **Chevauchement du scene-coder/smoke et du TTS** après matérialisation | 8–30 % si les ressources sont séparées | 4 | 3 | 1,5 | 8,0 | Retire directement `min(T_scene, T_TTS)` du chemin critique sans retirer d’étape qualité. |
| 4 | **Rendu Manim par scène dans 2–4 processus isolés**, avec concurrence Remotion fixée selon les quotas du pod | 15–40 % sur les jobs Manim dominés par le rendu ; 8–25 % sur Remotion actuellement mal réglé | 5 | 3 | 2 | 7,5 | Exploite les cœurs bare-metal tout en conservant résolution, FPS, code de scène et contrôles. |
| 5 | **Cache exact adressé par contenu pour le code, les scènes rendues, les WAV, l’alignement et les agrégats**, avec singleflight | 25–60 % d’une réparation ciblée ; environ 5–15 % de moyenne si 20 % des jobs réparent 1–2 scènes | 3 | 3 | 1,25 | 7,2 | Empêche les tentatives et jobs identiques de refaire un calcul coûteux ; aucune approximation sémantique n’est nécessaire. |

Ce classement favorise la facilité. En **impact brut maximal**, le rendu Manim parallèle passe devant le réglage LLM. Si le stockage de `/data/jobs` est aujourd’hui un volume réseau lent, le scratch NVMe local rejoint immédiatement le top 5. Si, au contraire, les prompts et narrations ne se répètent presque jamais, le cache inter-jobs descend dans le classement, mais le cache de réparation reste rentable.

### Décision recommandée

La meilleure trajectoire sans régression majeure est :

1. mesurer correctement le chemin critique ;
2. garder les mêmes modèles et les mêmes contrats, mais les maintenir chauds et correctement planifiés ;
3. faire tourner en parallèle uniquement les branches réellement indépendantes ;
4. rendre et cacher au niveau de la scène ;
5. ne tester modèles plus petits, quantification ou NVENC qu’après obtention de ces gains structurels.

## 1. Méthode, limites et niveau de confiance

### Fichiers et chemins inspectés

La cartographie repose principalement sur :

- `pipeline/production.py`, pour l’orchestration et les réparations ;
- `pipeline/materialize.py` et `pipeline/remotion_materialize.py`, pour le rendu et l’assemblage ;
- `pipeline/llm.py`, `pipeline/engine.py`, `pipeline/scene_coder.py` et `pipeline/remotion_scene_coder.py`, pour les appels LLM et smoke checks ;
- `pipeline/voice.py`, le script historique `generate_voice_en.py`, `pipeline/align.py` et `apps/tts-server/src`, pour la voix et l’alignement ;
- `pipeline/assets.py`, `pipeline/research.py`, `pipeline/verify.py` et `pipeline/visual_review.py` ;
- `tasks.py`, `celery_app.py`, `config.py`, les fichiers Compose et les Dockerfiles.

### Limites

- Aucun `report.json` de production réel n’était disponible localement. Les parts de temps de chaque étape sont donc inconnues.
- Le rapport actuel n’est pas une base de mesure complète : les durées sont calculées entre changements d’étape (`production.py:805-812`), mais la construction des timings intervient avant le passage à `completed` (`production.py:743-748`). La durée complète de `verify_final`, la finalisation et le webhook ne sont donc pas correctement représentés.
- Les gains dépendent fortement de la durée, du nombre de scènes, du moteur, du caractère chaud ou froid du pod, du TTS choisi, du taux de réparation et de la contention du cluster.
- Les gains « bout en bout » ne doivent pas être additionnés : plusieurs recommandations accélèrent la même portion du pipeline.

### Confiance

| Type de constat | Confiance |
|---|---|
| Ordre des étapes, concurrence et invalidations actuelles | Élevée : directement observés dans le code |
| Nature CPU/I/O/GPU des goulots | Élevée |
| Gain d’étape relatif, par exemple paralléliser 8 scènes | Moyenne |
| Gain bout en bout | Faible à moyenne avant baseline |
| Qualité inchangée avec modèle, paramètres, résolution et gates identiques | Élevée, sous réserve de déterminisme et de clés de cache correctes |
| Changement de modèle, quantification ou codec matériel | Faible sans évaluation de non-infériorité |

## 2. Cartographie complète du pipeline actuel

### 2.1 Chemin nominal

```text
FastAPI crée le job
  ↓
Celery prend une tâche monolithique
  ↓
initialisation / configuration / voix
  ↓
recherche optionnelle ─────────────── réseau
  ↓
blueprint : génération, traduction ou réparation ── LLM
  ↓
assets Remotion optionnels, scène après scène ───── réseau + disque
  ↓
motion preflight + validation Pydantic
  ↓
matérialisation du workspace
  ↓
scene-coder + validation + smoke checks ─────────── LLM + CPU/RAM
  ↓
TTS segment par segment ─────────────────────────── CPU/GPU/réseau
  ↓
alignement et cues Remotion ─────────────────────── CPU/GPU
  ↓
rendu Manim ou Remotion ─────────────────────────── CPU/RAM/disque
  ↓
mastering + loudnorm + mux ──────────────────────── CPU/disque
  ↓
revue visuelle optionnelle ──────────────────────── décodage + réseau
  ↓
ffprobe + freezedetect + snapshots + audio QC ───── CPU/disque
  ↓
rapport, statut terminal et webhook
```

Preuves principales :

- recherche avant la boucle de production : `production.py:239-256`, `312-315` ;
- blueprint/traduction/réparation : `production.py:380-445` ;
- assets Remotion : `production.py:458-468` ;
- motion preflight : `production.py:470-497` ;
- matérialisation : `production.py:507-508` ;
- scene-coder et validation : `production.py:516-535` ;
- TTS, après toute la branche scène : `production.py:537-565` ;
- alignement Remotion : `production.py:574-615` ;
- rendu, assemblage, revue et vérification : `production.py:632-709` ;
- reprise quasi complète après échec : `production.py:751-778`.

### 2.2 Concurrence et réutilisation déjà présentes

| Zone | Comportement actuel | Évaluation |
|---|---|---|
| Blueprint Remotion | Outline séquentiel puis scènes en parallèle avec `llm_parallel`, défaut 3 (`llm.py:1065-1320`) | Bonne base |
| Scene-coder Manim | Appels par scène via `ThreadPoolExecutor`; smoke renders limités à 2 (`engine.py:158-212`) | Bonne base |
| Scene-coder Remotion | Appels LLM par vagues, un `tsc` groupé, puis stills smoke séquentiels (`remotion_scene_coder.py:275-433`) | Partiellement optimisé |
| Assets | Recherche et téléchargement scène par scène (`assets.py:109-211`) | Séquentiel, I/O-bound |
| TTS local | Scènes synthétisées séquentiellement ; modèle local chargé par job | Goulot majeur potentiel |
| TTS MOSS distant | Modèle chaud, cache global et chemin batch, mais batch par défaut à 1 | Infrastructure utile sous-exploitée |
| Rendu Manim | Une commande pour toutes les classes, sans fan-out explicite (`materialize.py:497-532`) | CPU lourd peu distribué |
| Rendu Remotion | `--concurrency=75%`, CRF 18, x264 `faster` (`remotion_materialize.py:202-246`) | Déjà concurrent, réglage non lié au quota k3s |
| Assemblage | Vidéo copiée avec `-c:v copy`, audio AAC seulement réencodé | Déjà efficace |
| TTS cache | Empreintes segmentées, mais seulement dans le workspace (`voice.py:137-216`) | Bon pour une réparation locale |
| MOSS cache | CAS inter-jobs exact par texte/modèle/langue/référence | Bonne base à versionner davantage |
| Alignement | Cache au sein du job ; modèle MMS_FA reconstruit au premier miss du job | Partiellement optimisé |
| Multilingue | Secondaires mises en file ensemble après réussite complète du master (`tasks.py:25-74`) | Bon contrat, sous-exploité avec un worker |
| Celery | Une tâche monolithique par job ; worker à concurrence 1 ; `acks_late` et prefetch 1 | Sûr pour tâches longues, faible débit |

### 2.3 Classification des goulots

| Étape | Ressource dominante | Symptôme attendu | Priorité |
|---|---|---|---|
| Recherche, LLM, Pexels, vision, TTS distant | Réseau + service distant/local | Latence et temps de file, faible CPU du worker | Moyenne, sauf LLM/TTS |
| Chatterbox/Kokoro local | CPU et chargement modèle | Real-time factor élevé, cœur(s) saturé(s) | Très élevée |
| MOSS local/distant | GPU + file sérialisée | GPU chaud mais un seul consommateur ; batch 1 | Très élevée si ce moteur est utilisé |
| Smoke Manim/Remotion | CPU/RAM + démarrages de processus/Chrome/LaTeX | Nombreuses petites invocations | Élevée sur scènes Custom |
| Manim final | CPU + RAM, scènes peu distribuées | Long bloc séquentiel | Très élevée |
| Remotion final | CPU/RAM/Chrome + x264 | Sensible à la concurrence et aux quotas | Élevée |
| Alignement MMS_FA | Chargement modèle + CPU/GPU | Coût fixe par job | Moyenne |
| ffmpeg, revue, verify | CPU + plusieurs lectures du même MP4 | Décodages et processus répétés | Moyenne à faible |
| Workspace et médias | I/O local ou réseau | P95 instable, frames temporaires coûteuses | Élevée si le volume est distant |
| Redis/Postgres | Métadonnées et progression | Peu de volume comparé aux médias | Faible hors incident |

## 3. Axe 1 — Parallélisation

### 3.1 Chevaucher scene-coder/smoke et TTS

Après validation du blueprint, motion preflight et matérialisation, les deux branches consomment des données stables :

```text
materialize
  ├── scene-coder → validation statique ─┐
  └── TTS → durées audio ────────────────┤
                                        └── alignement → rendu
```

Le pipeline les sérialise actuellement. Le gain théorique est exactement `min(T_scene, T_TTS)`.

- **Gain bout en bout estimé :** 8–30 % avec scene-coder/Chrome sur CPU et TTS sur GPU séparé ; 0–10 % si les deux branches se disputent le même CPU ou GPU.
- **Risque :** faible à moyen.
- **Complexité :** moyenne.
- **Garde-fous :**
  - joindre les deux branches avant alignement et rendu ;
  - annuler proprement le TTS si la validation statique rend le job irrécupérable ;
  - publier WAV et `durations.json` atomiquement ;
  - ne jamais laisser l’alignement lire un manifeste partiel ;
  - ouvrir une session SQLAlchemy par branche ou sérialiser les mises à jour de progression dans le thread principal.

Ce dernier point est concret : les callbacks de progression Manim peuvent déjà remonter depuis le pool de threads et réutiliser la session du job (`production.py:520-529`, `engine.py:187-193`). Une `Session` partagée n’est pas thread-safe.

### 3.2 Rendre les scènes Manim en parallèle

La commande actuelle rend toutes les classes d’une vidéo puis concatène les MP4. Sur un nœud multi-cœurs, 2–4 processus indépendants, chacun avec son propre `media_dir`, permettent de distribuer les scènes sans changer leur contenu.

- **Gain de l’étape rendu :** 40–65 %.
- **Gain bout en bout :** 15–40 % si le rendu représente 40–70 % du job.
- **Risque :** moyen.
- **Complexité :** moyenne à élevée.
- **Contraintes :** même image, mêmes polices et LaTeX, même résolution 1080p60, mêmes durées, ordre de concaténation déterministe, plafond mémoire et concaténation `-c copy`.

Commencer dans un même pod avec 2, puis 4 processus est préférable à un Kubernetes Job par scène : le démarrage, le transfert des artefacts et un volume partagé peuvent sinon annuler le gain.

### 3.3 Exploiter la concurrence Remotion sans surallocation

Le défaut `75%` est calculé à partir des CPU visibles, qui peuvent différer du quota réellement utilisable dans un conteneur. Remotion avertit qu’une concurrence trop faible **ou trop élevée** ralentit le rendu ; sa recommandation est de benchmarker la valeur sur le workload réel ([Performance Tips](https://www.remotion.dev/docs/performance), [concurrency](https://www.remotion.dev/docs/terminology/concurrency)).

Recommandation :

- calculer un entier à partir de la limite CPU du pod ;
- réserver 1–2 cœurs à Node, ffmpeg et au système ;
- tester 1, 2, 4, 6, 8 et la valeur actuelle sur les mêmes compositions ;
- utiliser `resolvedConcurrency` et la télémétrie `renderedDoneIn`/`encodedDoneIn` pour distinguer Chrome de l’encodage.

- **Gain de rendu :** 15–40 % si `75%` suralloue ou sous-alloue aujourd’hui.
- **Gain bout en bout :** 8–25 % sur les jobs concernés.
- **Risque :** faible.
- **Complexité :** faible.

### 3.4 Parallélismes secondaires à borner

| Opportunité | Mise en œuvre sûre | Gain étape | Gain total | Risque |
|---|---|---:|---:|---|
| Assets Pexels | Sélectionner d’abord les scènes éligibles de façon déterministe, puis 2–4 recherches/téléchargements | 50–75 % | 1–8 % | Faible à moyen |
| Smoke stills Remotion | 2 stills simultanés maximum, répertoires isolés | 30–55 % | 2–10 % | Moyen, RAM Chrome |
| Revue visuelle et verify | Faire chevaucher au plus 2 décodages lourds et l’appel vision réseau | 25–50 % de cette phase | 1–6 % | Faible à moyen |
| Langues secondaires | Plusieurs pods Celery `concurrency=1` après réussite du master | 35–65 % du makespan batch | 0 % par vidéo primaire | Faible |

La barrière du blueprint maître doit rester en place : une langue secondaire traduit le blueprint validé, elle ne doit ni anticiper un master non viable ni régénérer un contenu différent.

### 3.5 Ce qu’il ne faut pas paralléliser naïvement

- Le premier segment MOSS reste une barrière lorsqu’il sert de référence aux suivants (`tts_server/jobs.py:228-239`).
- Plusieurs jobs TTS sur un seul GPU ne créent pas mécaniquement du débit : le serveur actuel sérialise l’accès au moteur (`jobs.py:200-218`, `engine.py:147-170`).
- Augmenter `llm_parallel`, la concurrence Celery et les replicas TTS en même temps masque la cause des ralentissements et favorise OOM, préemptions KV et contention.
- Le scene-coder Remotion et l’alignement ne doivent pas écrire simultanément le même `scenes_map.json`.
- Les contrôles finaux doivent tous terminer avant publication du job.

## 4. Axe 2 — Cache et réutilisation

### 4.1 État actuel

Le cache TTS job-local est segmenté : la signature de voix et le texte produisent une empreinte, les WAV identiques sont réutilisés, et les materializers préservent `audio/` lors d’une réparation (`voice.py:137-216`, `materialize.py:669-681`). Le serveur MOSS possède en plus un CAS global et persistant. L’alignement possède un cache local. Les langues secondaires réutilisent le blueprint et le dossier de recherche du master.

En revanche, les materializers effacent les rendus et une grande partie des sources générées à chaque tentative (`materialize.py:669-674`, `remotion_materialize.py:274-294`). Il n’existe pas de cache global apparent pour le blueprint, les assets, le code validé, le smoke attesté, les MP4 par scène, l’agrégat audio ou le résultat final.

### 4.2 Cache de code et de rendu par scène

Deux niveaux indépendants sont recommandés :

1. **code validé**, indexé par la spécification complète de la scène ;
2. **rendu de scène**, indexé par le code, la durée audio et tout l’environnement visuel.

Clé minimale du code :

```text
engine + JSON canonique de la scène + contexte global utile
+ langue + modèle/révision/paramètres
+ hash des prompts, guidelines, skill, catalogue et runtime
+ version des schémas et validateurs
```

Clé minimale du rendu :

```text
hash du code + style partagé + texte/beats + durée audio réelle
+ SHA-256 des assets + résolution/FPS/qualité
+ versions Manim ou Remotion, Python/Node, ffmpeg, LaTeX et polices
+ digest de l'image de conteneur
```

- **Gain scene-coder/rendu sur une réparation de 1–2 scènes sur 8 :** 60–90 %.
- **Gain de l’itération réparée :** 25–60 %.
- **Gain moyen illustratif :** 5–15 % si 20 % des jobs passent par une telle réparation.
- **Risque :** faible à moyen avec une clé exhaustive ; élevé avec une clé incomplète.
- **Complexité :** moyenne pour le code, élevée pour le rendu.

La validation statique doit toujours repasser. Un smoke peut être réutilisé seulement si l’attestation inclut exactement le digest du runtime.

### 4.3 CAS TTS global

Étendre le principe du serveur MOSS aux moteurs locaux et OpenAI-compatible permettrait de réutiliser des WAV exacts hors du workspace. La clé doit inclure :

```text
engine + modèle + révision résolue + version du générateur
+ voix + langue + texte selon la canonicalisation propre au moteur
+ vitesse + paramètres de sampling/prosodie
+ SHA-256 du WAV de référence
+ format + sample rate + canaux + profil de synthèse versionné
```

Avant toute globalisation, plusieurs faiblesses du cache local doivent être corrigées conceptuellement :

- la signature actuelle capture surtout le chemin/les valeurs, pas le contenu du fichier de référence ;
- la source/version de `generate_voice_en.py` n’est pas dans la clé ;
- la normalisation par espaces peut fusionner des textes dont les retours à la ligne influencent Kokoro ;
- une empreinte tronquée à 16 caractères est trop courte pour un CAS durable à grande échelle ;
- le CAS MOSS doit inclure la révision résolue, le dtype et le profil de décodage.

- **Gain TTS sur un hit :** 70–95 %.
- **Gain moyen :** approximativement `taux_de_hit × part_TTS`.
- **Risque :** faible avec correspondance exacte et objets immuables.
- **Complexité :** moyenne.

Un cache sémantique ou « texte proche » est exclu : une petite différence de narration doit produire un nouvel audio.

### 4.4 Agrégats audio et alignement

Même si tous les WAV bruts sont réutilisés, le pipeline relance actuellement `ffprobe`, padding, concaténation et encodage MP3 (`generate_voice_en.py:601-653`).

À cacher :

- durée brute par SHA-256 du WAV ;
- WAV paddé par `(hash, tail_padding, format)` ;
- agrégat PCM par liste ordonnée d’empreintes ;
- alignement par `(SHA-256 WAV, tokens normalisés, modèle MMS_FA, version du normaliseur)`.

- **Gain du post-traitement audio résiduel avec 100 % de WAV hits :** 40–80 %.
- **Gain alignement sur hit :** 70–95 %.
- **Gain bout en bout cumulé :** 1–8 % typique, plus sur des réparations.
- **Risque :** faible.
- **Complexité :** faible à moyenne.

### 4.5 Recherche, assets, blueprint et résultat final

| Cache | Clé/fraîcheur | Gain sur hit | Gain total probable | Recommandation |
|---|---|---:|---:|---|
| Recherche | Provider, requête, limites, paramètres, version du normaliseur ; TTL court | 80–95 % de l’étape | 1–5 % | Oui, exact et expirant |
| Sélection Pexels | Requête, type, orientation, algorithme ; TTL court | 70–95 % | 1–8 % | Oui, conserver provenance/licence |
| Blob média | URL/rendition/ETag puis SHA-256 ; TTL long | 70–95 % | 1–8 % | Oui |
| Blueprint | Prompt exact, durée, langue, thème, config, recherche, modèle/révision, prompts et schéma | 90–99 % du planning | 2–12 % | Oui si trafic répétitif |
| MP4 final | Toutes les entrées et tout le runtime, plus versions de QC | 90–99 % du job | `≈ taux_de_doublon × 90–99 %` | Seulement après mesure des doublons |

Le blueprint ne doit jamais utiliser une similarité vectorielle approximative : deux questions STEM proches peuvent avoir des faits, sources et objectifs pédagogiques différents. Un résultat de quality gate ne peut être réutilisé que pour le même hash MP4 et les mêmes versions de seuils, prompt vision et modèle.

### 4.6 Architecture de cache k3s

- **L1 :** NVMe local du nœud pour WAV, bundles, code et MP4 de scènes chauds.
- **L2 :** objet-store auto-hébergé ou RWX mesuré pour les blobs utiles à plusieurs nœuds.
- **Singleflight :** verrou Redis `SET NX` ou équivalent pour qu’une seule synthèse ou un seul rendu remplisse une clé.
- **Publication :** fichier temporaire, validation, `fsync`, renommage atomique ; jamais d’objet partiellement visible.
- **Consommation :** hardlink/reflink en lecture seule sur le même filesystem, copie vérifiée sinon.
- **Validation d’un hit :** entête WAV ou `ffprobe` avant utilisation.
- **Rétention :** quotas et LRU/TTL distincts du GC de `/data/jobs`, qui expire les workspaces.
- **Observabilité :** hit/miss, invalidation, attente singleflight, octets et secondes de calcul évités par niveau.

## 5. Axe 3 — Optimisation LLM

### 5.1 Cartographie

- Manim génère un blueprint complet avec un long exemple statique ; une invalidité entraîne une réparation complète (`llm.py:721-826`).
- Remotion utilise par défaut deux passes : outline, puis une requête parallèle par scène, jusqu’à deux essais, validation globale et réparation éventuelle (`llm.py:1065-1320`).
- Si le chemin two-pass lève une exception générale, son travail peut être abandonné au profit d’un single-pass complet (`llm.py:978-1003`).
- La traduction renvoie elle aussi un blueprint complet et répare globalement une réponse invalide (`llm.py:829-949`).
- Le même modèle sert au blueprint, à l’expansion, à la traduction et aux réparations ; seul le scene-coder possède déjà une option de modèle distincte.
- Le raisonnement caché est désactivé par défaut, ce qui est cohérent avec une génération structurée.

Les préfixes statiques sont importants : environ 14,7 k caractères pour le blueprint Manim, 7,7–9,2 k pour les prompts Remotion, 11,1 k pour le skill scene-coder Manim et 17,1 k pour le skill Custom Remotion. Cela rend le cache de préfixe pertinent.

### 5.2 Concurrence et continuous batching

Les requêtes par scène existent déjà. Le prochain gain consiste à accorder leur concurrence au serveur local :

- benchmarker 1, 2, 3, 4, 6 et 8 requêtes ;
- mesurer makespan, TTFT, tokens/s agrégés, P95, préemptions KV et VRAM ;
- activer/utiliser le continuous batching côté serveur ;
- isoler le GPU LLM du GPU TTS lorsque les deux services sont simultanés.

Avec 8 scènes, passer de 3 à 4 requêtes peut réduire trois vagues à deux. Mais au-delà du point de saturation, la concurrence dégrade la latence.

- **Gain des appels par scène :** 20–50 %.
- **Gain bout en bout :** 5–15 %.
- **Risque :** faible à moyen.
- **Complexité :** faible.

### 5.3 Cache exact de préfixe

Le cache KV de préfixe ne change ni modèle ni tokens générés. vLLM précise qu’il accélère le **prefill**, pas le décodage ([Automatic Prefix Caching](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/)). Il faut donc placer les blocs statiques au début et les données de scène à la fin.

Le custom scene-coder Remotion injecte actuellement une clé de scène avant un long skill statique, ce qui détruit une grande partie du préfixe partagé (`remotion_scene_coder.py:68-81`, `215-235`). Les traductions placent aussi la langue cible avant un blueprint partagé.

- **Réduction du prefill :** 50–90 % sur un hit chaud.
- **Réduction de l’étape LLM entière :** 5–25 %, selon la part de décodage.
- **Gain bout en bout :** 1–8 %.
- **Risque :** faible.
- **Complexité :** faible à moyenne.

### 5.4 JSON Schema strict, Pydantic conservé

Le mode actuel `json_object` garantit surtout la syntaxe. Les champs, types et enums restent découverts par Pydantic, parfois après un appel complet. Si l’endpoint supporte les structured outputs stricts, le schéma JSON de `VideoBlueprint` ou `RemotionBlueprint` peut supprimer une partie des erreurs structurelles.

La validation métier Pydantic doit rester inchangée : durée globale, nombre de scènes, budget narratif, ordre, anchors verbatim et contraintes pédagogiques dépassent un simple schéma.

- **Gain du coût des réparations structurelles :** 50–90 %.
- **Gain total :** 1–8 % en moyenne ; 15–30 % sur un job aujourd’hui invalide pour une erreur purement structurelle.
- **Risque :** faible à moyen, selon la compatibilité réelle de l’endpoint.
- **Complexité :** moyenne.

Les recommandations de schéma strict et de préfixe statique sont cohérentes avec les guides officiels [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) et [Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching).

### 5.5 Checkpoints et réparations ciblées

Le two-pass doit persister l’outline et chaque scène validée. En cas de timeout ou d’erreur d’une scène, seules les scènes manquantes doivent repartir. De même, un repair devrait demander un patch ciblé ou une scène, puis revalider le blueprint complet, plutôt que régénérer toute la réponse.

- **Gain sur un chemin d’échec partiel :** 40–80 % de l’étape LLM.
- **Gain moyen :** 0–10 %, directement proportionnel au taux d’échec.
- **Risque :** faible si la validation globale reste obligatoire.
- **Complexité :** moyenne.

### 5.6 Routage de modèle et speculative decoding

Le routage sûr est un **cascade avec fallback**, pas un remplacement global :

- modèle le plus capable pour outline pédagogique, code complexe et réparation après échec qualité ;
- modèle plus rapide pour traduction contrainte ou expansion de scènes ;
- remontée automatique au modèle fort si Pydantic, rubric ou smoke échoue.

- **Gain des appels routés :** 30–65 %.
- **Gain total potentiel :** 5–20 %.
- **Risque :** moyen à élevé sans corpus d’évaluation.
- **Complexité :** moyenne.

Le speculative decoding du même modèle cible peut réduire le décodage sans accepter la sortie d’un modèle différent. La documentation vLLM recommande cependant de le benchmarker pour la topologie et la charge réelles ([Speculative decoding](https://docs.vllm.ai/en/stable/features/spec_decode/)).

- **Gain du décodage :** 15–40 %.
- **Gain total :** 3–12 %.
- **Risque :** moyen opérationnel.
- **Complexité :** moyenne à élevée.

### 5.7 Faibles priorités

- Le streaming améliore le premier token et la progression, mais un blueprint JSON doit être complet et validé avant utilisation : gain mur proche de 0 seul.
- Regrouper toutes les scènes dans une seule requête réduit le nombre d’appels mais sérialise leur décodage et agrandit le domaine d’échec.
- Réduire la narration accélérerait le LLM et le rendu seulement en raccourcissant la vidéo : c’est une dégradation produit, pas une optimisation.
- Un plafond de sortie par opération borne les runaway et le P99, mais n’accélère pas une réponse qui produit déjà EOS normalement.

## 6. Axe 4 — Rendu vidéo

### 6.1 Manim

Le rendu final Manim est fixé à 1080p60 et la concaténation ne réencode pas la vidéo. Les optimisations compatibles avec la qualité sont donc :

1. parallélisme par scène borné ;
2. cache de scène exact ;
3. réutilisation des scènes inchangées lors d’un repair ;
4. scratch NVMe local ;
5. préchauffage des caches LaTeX/polices sans partager des répertoires d’écriture concurrents.

Le cache natif Manim fondé sur les play calls est utile dans un workspace stable, mais la suppression de `media/` à chaque tentative empêche d’en tirer tout le bénéfice. Manim documente ce mécanisme de cache et les sorties partielles dans ses guides [Output and configuration](https://docs.manim.community/en/stable/tutorials/output_and_config.html) et [deep dive](https://docs.manim.community/en/stable/guides/deep_dive.html).

Il ne faut ni passer le final à 720p, ni réduire les 60 fps, ni remplacer les attentes pilotées par la durée audio par des délais arbitraires.

### 6.2 Remotion

Le projet verrouille actuellement Remotion et son lockfile à `4.0.400`. Les priorités sont :

- concurrence entière liée au quota CPU ;
- bundle unique par version du runtime ;
- navigateur ouvert réutilisé pour les stills d’une vague ;
- deux stills smoke simultanés au maximum ;
- cache des scènes Custom et de leurs attestations.

L’API `renderMedia()` accepte un bundle existant et un `puppeteerInstance` réutilisable ; la documentation indique explicitement que cette réutilisation peut accélérer plusieurs rendus ([renderMedia](https://www.remotion.dev/docs/renderer/render-media)).

- **Gain smoke avec bundle/navigateur chaud :** 40–80 %.
- **Gain bout en bout des jobs Custom :** 3–15 %.
- **Risque :** faible à moyen, surtout fuite mémoire/état entre rendus.
- **Complexité :** moyenne.

### 6.3 ffmpeg, revue et contrôles

La revue visuelle extrait trois frames par scène dans des processus séparés, puis `verify` refait un décodage complet, cinq extractions et une passe audio. Des graphes `filter_complex` ou un service d’extraction borné peuvent mutualiser les lectures :

- un passage pour les timestamps de revue et snapshots compatibles ;
- `freezedetect` et extraction sans dépasser deux décodages simultanés ;
- appel vision en parallèle du QC CPU, avec barrière finale.

- **Gain revue + vérification :** 30–70 % de cette phase.
- **Gain bout en bout :** 3–12 % dans les jobs où la revue est active.
- **Risque :** faible à moyen.
- **Complexité :** moyenne.

Le mux est déjà bien optimisé : `-c:v copy` évite un réencodage vidéo. Le loudnorm deux passes, le mastering, la piste AAC finale et les validations audio doivent rester.

### 6.4 Manim ou Remotion ?

Un basculement global vers un moteur prétendument « plus rapide » est déconseillé : les deux moteurs n’ont pas les mêmes primitives ni la même qualité pour les transformations mathématiques.

Un routage futur fondé sur un benchmark peut être étudié :

- Remotion pour DOM/SVG, code, diagrammes, footage et typographie ;
- Manim pour transformations mathématiques continues et géométrie analytique.

Mais le routage doit être décidé avant le blueprint, validé sur la même rubrique pédagogique, et ne pas devenir un fallback silencieux qui change le sens visuel.

- **Gain potentiel sur jobs compatibles :** 10–35 %.
- **Risque :** moyen à élevé.
- **Complexité :** moyenne à élevée.
- **Priorité :** après les optimisations intra-moteur.

### 6.5 Encodage matériel et résolution adaptative

La documentation Remotion actuelle précise que NVENC sous Linux/Windows demande la version `4.0.484` ou ultérieure ; le dépôt est en `4.0.400`. Une mise à niveau serait donc préalable. NVENC n’accepte pas le CRF et exige un bitrate ; Remotion conseille de contrôler explicitement taille et qualité ([Hardware accelerated encoding](https://www.remotion.dev/docs/hardware-acceleration)).

- **Accélération de l’encodage seul :** 2–5×.
- **Gain bout en bout probable :** 3–12 %, car Chrome/frame rendering domine souvent.
- **Risque :** moyen : changement de codec effectif, taille, qualité et upgrade runtime.
- **Complexité :** moyenne.

Ce n’est pas un top 5. Il ne faut pas partager le seul GPU TTS avec NVENC. Un essai nécessiterait VMAF/SSIM, inspection des textes/formules et comparaison de taille.

La résolution adaptative n’est acceptable que pour un **préflight non livrable**. Rendre le final en 720p puis l’agrandir dégrade textes et formules et viole le contrôle 1920×1080. Le profil final doit conserver la résolution et le FPS contractuels.

## 7. Axe 5 — TTS et audio

### 7.1 Goulot principal

Chatterbox non-turbo est le moteur par défaut. Sous Linux, le script sélectionne MPS si disponible, sinon CPU ; il ne choisit pas CUDA (`generate_voice_en.py:126-149`). Le modèle est chargé dans le subprocess de chaque job, puis les scènes sont synthétisées séquentiellement.

Le modèle Chatterbox officiel prend en charge CUDA ([documentation du modèle](https://www.resemble.ai/learn/models/chatterbox)). La recommandation de qualité neutre est donc un service persistant utilisant **le même checkpoint Chatterbox, la même voix et les mêmes paramètres** sur NVIDIA GPU. Remplacer Chatterbox par MOSS ou Kokoro n’est pas supposé neutre et exige un test aveugle séparé.

- **Gain de l’étape TTS par rapport au chemin CPU/rechargé :** 60–95 %.
- **Gain bout en bout :** 15–45 %, jusqu’à environ 55 % si le TTS domine réellement.
- **Risque :** faible à moyen avec le même modèle ; vérifier le comportement stochastique et la parité audio.
- **Complexité :** moyenne.

### 7.2 Exploiter le serveur MOSS existant

Le service MOSS :

- garde le modèle en mémoire ;
- expose une readiness après chargement ;
- possède un cache WAV inter-jobs ;
- sait appeler `model.generate` sur un batch ;
- sérialise l’accès GPU, ce qui est cohérent pour un modèle lourd.

Mais `TTS_SERVER_BATCH_SIZE` vaut 1. Tester 2 puis 4 est le premier levier. Une référence approuvée et fixe évite que le premier segment généré soit la barrière/empreinte de tous les suivants. Regrouper les segments de longueur voisine évite qu’un texte long fixe le plafond du batch entier.

- **Gain de synthèse MOSS :** 35–65 % avec batch 2–4.
- **Gain bout en bout :** 10–30 % selon la part TTS.
- **Risque :** faible à moyen ; le batching peut modifier les tirages.
- **Complexité :** faible à moyenne.

Le modèle MOSS-TTS v1.5 documente le batching et recommande FlashAttention 2 sur matériel compatible ([model card](https://huggingface.co/OpenMOSS-Team/MOSS-TTS-v1.5)). FlashAttention peut réduire temps/mémoire, mais son gain doit rester une mesure secondaire après le batch.

### 7.3 Pipeline de téléchargement et post-traitement

Le client MOSS attend aujourd’hui la fin globale avant de télécharger les WAV. Il pourrait consommer les segments terminés, valider leurs entêtes, calculer durée/padding et préparer l’alignement pendant que le GPU produit le batch suivant.

- **Gain de la chaîne TTS/audio :** 10–25 %.
- **Gain total :** 3–10 %.
- **Risque :** faible avec manifestes atomiques.
- **Complexité :** moyenne.

### 7.4 Supprimer les MP3 intermédiaires

Le chemin actuel crée des MP3 par segment, concatène un WAV, encode un MP3 global, puis le décode pour mastering/loudnorm et l’encode enfin en AAC. Le chemin sans perte intermédiaire est :

```text
WAV PCM16 segment
  → padding/concaténation PCM
  → mastering et loudnorm deux passes
  → AAC final
```

Cela retire des encodages et évite MP3 → PCM → AAC. C’est à la fois plus rapide et légèrement meilleur pour la qualité.

- **Gain du post-traitement audio :** 40–80 %.
- **Gain bout en bout :** 1–5 % dans un job normal.
- **Risque :** très faible.
- **Complexité :** moyenne.

Sur un LAN bare-metal, quatre minutes de PCM16 mono 24 kHz représentent environ 11,5 MB : une compression lossy réseau ne se justifie pas. Si le stockage mesuré est réellement le goulot, FLAC est le candidat sans perte.

### 7.5 Aligneur chaud

MMS_FA est construit au premier cache miss de chaque appel/job. Le maintenir chaud dans un petit service ou worker, avec cache global versionné, retire ce coût fixe sans supprimer la synchronisation.

- **Gain alignement :** 30–80 % à chaud, 70–95 % sur hit exact.
- **Gain total :** 1–8 %.
- **Risque :** faible.
- **Complexité :** moyenne.

La suppression de l’alignement n’est pas acceptable : la synchronisation narration/visuel est un contrat qualité central.

## 8. Axe 6 — Infrastructure bare-metal k3s

### 8.1 Topologie recommandée

```text
                 ┌───────────────────────────────┐
API / Postgres / │ Redis + files Celery + Beat  │
                 └──────────────┬────────────────┘
                                │
              ┌─────────────────┴──────────────────┐
              │                                    │
     pool CPU rendu                         pool GPU services
  Manim / Remotion / ffmpeg              TTS chaud / LLM chaud
  1 job lourd par pod                    1 modèle par GPU logique
  scratch NVMe local                     cache modèle local
              │                                    │
              └───────── publication/CAS ──────────┘
                    stockage durable auto-hébergé
```

Recommandations :

- pods Manim/Remotion avec requests et limits CPU/mémoire explicites ;
- un processus Celery lourd par pod, plutôt qu’une forte concurrence dans le même worker ;
- nœuds GPU étiquetés/taintés, demande `nvidia.com/gpu: 1`, readiness seulement après chargement ;
- un replica de modèle par GPU physique sauf preuve qu’un partage est sûr ;
- Celery Beat dans un déploiement singleton : le worker Compose embarque actuellement `--beat`, qu’il ne faut pas répliquer tel quel ;
- files séparées par classe de ressource à terme, sans changer le contrat master/secondaires.

Kubernetes expose les GPU via device plugins et ressources étendues ; les demandes se placent dans `limits` et peuvent être combinées avec labels et affinité ([Scheduling GPUs](https://kubernetes.io/docs/tasks/manage-gpus/scheduling-gpus/), [Device Plugins](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/device-plugins/)).

### 8.2 Scratch local et stockage durable

Les frames, médias intermédiaires, caches LaTeX et rendus de scène doivent vivre sur NVMe local (`emptyDir` adossé au disque ou PV local), puis seuls MP4 final, rapport, sous-titres et blobs CAS utiles sont promus atomiquement.

- **Gain bout en bout :** 5–25 % si le workspace est actuellement sur NFS/Ceph lent ; presque nul s’il est déjà en NVMe.
- **Effet principal :** baisse de variance P95 et de contention.
- **Risque :** moyen : rescheduling et perte du scratch après panne.
- **Complexité :** moyenne à élevée.

Un volume local Kubernetes doit avoir une `nodeAffinity`, et `WaitForFirstConsumer` évite un binding incompatible avec le pod ([Volumes](https://kubernetes.io/docs/concepts/storage/volumes/)). Le scratch reste éphémère ; les checkpoints nécessaires à une reprise doivent être promus.

### 8.3 Files et workers

`worker_prefetch_multiplier=1` et `acks_late=True` sont déjà adaptés aux tâches longues. Celery recommande ce type de réglage et des workers séparés pour charges longues/courtes ([Optimizing](https://docs.celeryq.dev/en/stable/userguide/optimizing.html)).

Court terme :

- plusieurs replicas `concurrency=1` pour augmenter le débit ;
- quotas empêchant deux rendus lourds de saturer le même nœud ;
- Beat séparé ;
- files CPU et GPU distinctes si les services sont découplés.

Long terme :

- checkpoints idempotents `plan`, `TTS`, `render`, `postprocess` ;
- files et autoscaling distincts ;
- reprise au dernier artefact validé.

Le découpage peut augmenter le débit soutenu de 1,5–2,5× et réduire l’attente sous charge de 30–60 %, mais il change peu la latence à vide. Sa complexité est élevée ; il vient après le parallélisme intra-job et le cache.

### 8.4 Pré-warming et placement

- maintenir au moins un replica TTS prêt ;
- pré-puller l’image lourde Manim/TeX/Chrome ;
- préamorcer localement les checkpoints HF/Torch sur le nœud GPU ;
- garder bundle et navigateur Remotion chauds dans une durée de vie bornée ;
- ne pas partager le seul GPU entre LLM, MOSS et NVENC ;
- mesurer CPU Manager/Topology Manager seulement sur machines bi-socket et sous contention.

Le pré-warming économise des dizaines de secondes à plusieurs minutes sur un pod froid, mais presque rien à chaud. Il améliore surtout P95/P99.

### 8.5 Quantification

La quantification n’est pas une optimisation prioritaire de latence :

- int8 peut réduire la VRAM et permettre un batch supérieur, mais sa vitesse peut varier d’environ −10 à +30 % selon kernels et GPU ;
- elle peut modifier timbre, prosodie ou prononciation TTS ;
- un modèle LLM 4-bit peut modifier les blueprints et le code ;
- charger plusieurs modèles qui se remplacent sur un seul GPU peut coûter plus que le gain.

Recommandation : BF16/FP16 comme baseline, int8 seulement en expérimentation de capacité avec test de non-infériorité ; 4-bit TTS écarté tant qu’une validation audio robuste n’existe pas.

## 9. Matrice consolidée gains / risques / complexité

Les gains totaux sont des plages conditionnelles, non cumulables.

| ID | Optimisation | Gain d’étape estimé | Gain bout en bout estimé | Risque | Complexité | Confiance |
|---|---|---:|---:|---|---|---|
| P1 | TTS en parallèle du scene-coder/smoke | Économie `min(A,B)` | 8–30 % | Faible–moyen | Moyenne | Moyenne |
| P2 | Manim, 2–4 processus par scène | 40–65 % rendu | 15–40 % | Moyen | Moyenne–élevée | Moyenne |
| P3 | Assets, 2–4 requêtes déterministes | 50–75 % assets | 1–8 % | Faible–moyen | Faible–moyenne | Moyenne |
| P4 | Smoke stills Remotion ×2 | 30–55 % smoke | 2–10 % | Moyen | Faible–moyenne | Moyenne |
| P5 | QC/revue bornés et mutualisés | 25–70 % phase | 1–12 % | Faible–moyen | Moyenne | Moyenne |
| P6 | Secondaires multilingues sur plusieurs pods | 35–65 % makespan batch | 0 % primaire ; 35–65 % batch secondaire | Faible | Faible–moyenne | Élevée |
| C1 | Cache code + rendu par scène | 60–90 % sur hit | 25–60 % réparation ; 5–15 % moyenne illustrative | Faible–moyen | Moyenne–élevée | Moyenne |
| C2 | CAS WAV global exact | 70–95 % TTS sur hit | `hit × part_TTS` | Faible | Moyenne | Élevée sur hit |
| C3 | Cache durées/padding/agrégat | 40–80 % post-audio sur hit | 1–8 % | Faible | Faible–moyenne | Moyenne |
| C4 | Cache alignement + modèle chaud | 70–95 % sur hit | 1–8 % | Faible | Moyenne | Moyenne |
| C5 | Recherche/assets exacts | 70–95 % sur hit | 1–8 % | Faible–moyen | Moyenne | Moyenne |
| C6 | Blueprint/final exact + singleflight | 90–99 % sur hit | Dépend du taux de doublon | Moyen | Moyenne–élevée | Faible avant métriques |
| L1 | Concurrence LLM + continuous batching | 20–50 % appels scène | 5–15 % | Faible–moyen | Faible | Moyenne |
| L2 | Cache exact de préfixe | 50–90 % prefill | 1–8 % | Faible | Faible–moyenne | Élevée sur prefill |
| L3 | JSON Schema strict + Pydantic | 50–90 % repairs structurels | 1–8 % moyen | Faible–moyen | Moyenne | Moyenne |
| L4 | Checkpoint two-pass et repair ciblé | 40–80 % chemin d’échec | 0–10 % | Faible | Moyenne | Moyenne |
| L5 | Cascade de modèles avec fallback | 30–65 % appels routés | 5–20 % | Moyen–élevé | Moyenne | Faible avant eval |
| L6 | Speculative decoding | 15–40 % décodage | 3–12 % | Moyen | Moyenne–élevée | Faible–moyenne |
| R1 | Concurrence Remotion liée au quota | 15–40 % rendu si mal réglé | 8–25 % | Faible | Faible | Moyenne |
| R2 | Bundle + navigateur Remotion chauds | 40–80 % smoke | 3–15 % Custom | Faible–moyen | Moyenne | Moyenne |
| R3 | NVENC après upgrade et validation | 2–5× encodage | 3–12 % | Moyen | Moyenne | Faible avant benchmark |
| T1 | Service GPU persistant, même TTS | 60–95 % TTS | 15–45 % | Faible–moyen | Moyenne | Moyenne |
| T2 | MOSS batch 2–4 + bucketing | 35–65 % synthèse | 10–30 % | Faible–moyen | Faible–moyenne | Moyenne |
| T3 | Téléchargement/post-traitement progressif | 10–25 % chaîne audio | 3–10 % | Faible | Moyenne | Moyenne |
| T4 | PCM jusqu’à l’AAC final | 40–80 % post-audio | 1–5 % | Très faible | Moyenne | Élevée |
| I1 | Scratch NVMe local | Variable | 5–25 % si stockage réseau | Moyen | Moyenne–élevée | Faible avant mesure |
| I2 | Pods dédiés avec quotas exacts | 10–30 % sous contention | P95 surtout | Faible | Moyenne | Moyenne |
| I3 | Modèles/images préchauffés | Coût froid largement évité | Fort à froid, nul à chaud | Faible | Faible–moyenne | Élevée |
| I4 | Files par étape/checkpoints | Débit 1,5–2,5× sous charge | Latence à vide faible | Moyen | Élevée | Faible–moyenne |
| I5 | Quantification TTS/LLM | −10 à +30 % possible | Inconnu | Élevé | Élevée | Faible |

## 10. Optimisations explicitement déconseillées

- Réduire le final à 720p, upscaler, ou diminuer les 60 fps contractuels.
- Raccourcir la narration pour réduire les tokens ou le nombre de frames.
- Remplacer Chatterbox par Kokoro/MOSS, ou un modèle LLM par un plus petit, en supposant la qualité équivalente.
- Désactiver validation Pydantic, static checks, smoke, visual review, `freezedetect`, audio QC, mastering, loudnorm ou alignement.
- Augmenter aveuglément toutes les concurrences.
- Utiliser un cache sémantique pour le blueprint, le code ou la voix.
- Rendre directement les frames temporaires sur un stockage réseau lent.
- Quantifier en 4-bit le TTS de production sans protocole audio.
- Utiliser NVENC sur le seul GPU TTS ou sans validation texte/formules.
- Lancer les langues secondaires avant validation complète du blueprint maître.
- Remplacer globalement Manim par Remotion uniquement pour la vitesse.

## 11. Prochaines étapes recommandées

### Phase 0 — Baseline et critères d’acceptation

Avant tout changement :

1. corriger conceptuellement la couverture des timings pour inclure chaque étape, tentative et finalisation ;
2. instrumenter temps de file, temps de service, attente de sémaphore et cold start ;
3. constituer un corpus stable ;
4. exécuter une seule campagne de baseline, puis comparer chaque variante par A/B.

Corpus minimal :

- 30–50 prompts STEM : mathématiques, physique, informatique, ingénierie ;
- 60 s et 240 s, 8–12 scènes ;
- Manim et Remotion, scènes Custom et catalogue ;
- recherche/assets activés et désactivés ;
- anglais, français et au moins deux langues non latines ;
- TTS local et distant ;
- pod froid/chaud, succès premier passage et réparation ciblée ;
- au moins 10–20 répétitions par cellule critique, P50/P95.

Mesures :

- LLM : TTFT, prefill, decode, tokens/s, tokens cachés, retries, first-pass Pydantic, fallback ;
- TTS : chargement, queue, batch, RTF, secondes audio, cache, VRAM, warnings de cap ;
- rendu : temps par scène, frames/s, CPU/RSS, temps Chrome et encodage séparés ;
- I/O : octets, débit, latence, temps NVMe/PVC ;
- cache : hit/miss, invalidation, attente singleflight, secondes évitées ;
- qualité : résultats des gates et causes de réparation.

### Phase 1 — Gains rapides sans changement de contrat

1. benchmarker Chatterbox identique CPU actuel versus service CUDA chaud ;
2. pour MOSS, tester batch 1/2/4, référence fixe et longueurs regroupées ;
3. benchmarker concurrence LLM 1/2/3/4/6 et activer le cache de préfixe exact ;
4. benchmarker Remotion avec des entiers liés au quota ;
5. comparer scratch NVMe et stockage partagé ;
6. isoler Beat avant toute réplication des workers.

Critère de sortie : amélioration P50/P95 reproductible, sans dégradation des gates.

### Phase 2 — Chemin critique et réutilisation

1. faire chevaucher scene-coder/smoke et TTS avec écritures atomiques ;
2. rendre Manim par scène avec 2 puis 4 slots ;
3. préserver les scènes propres durant un repair ;
4. introduire le CAS exact pour code, rendu, WAV, agrégat et alignement ;
5. ajouter singleflight et métriques de hit.

Critère de sortie : aucun artefact partiel, reprise déterministe et mêmes MP4/audio à tolérance définie.

### Phase 3 — Optimisations conditionnelles

1. structured outputs stricts et repairs ciblés ;
2. bundle/navigateur Remotion persistants ;
3. files Celery par ressource et checkpoints idempotents ;
4. cascade de modèles seulement après eval ;
5. NVENC seulement après upgrade Remotion, benchmark et qualité ;
6. quantification uniquement comme expérience de capacité.

## 12. Garde-fous de non-régression

### Visuel et synchronisation

- résolution et FPS finaux inchangés ;
- aucun retrait de scène ou réduction arbitraire de durée ;
- mêmes seuils `ffprobe`, `freezedetect`, snapshots et revue visuelle ;
- cues et sous-titres toujours dérivés de l’audio réel ;
- inspection de plusieurs frames, notamment formules, petits textes et transitions ;
- pour un changement de codec : VMAF/SSIM comme filtres, plus inspection humaine, car ces métriques peuvent mal refléter la lisibilité de texte.

### Audio

- même modèle/voix/paramètres pour déclarer une optimisation « neutre » ;
- WER ASR et lexique STEM ;
- similarité de locuteur ;
- MOS/MUSHRA aveugle sur prosodie, pauses et prononciation ;
- loudness, true peak, clipping et silences ;
- loudnorm deux passes et AAC final conservés.

### LLM et éditorial

- taux de blueprint valide au premier passage ;
- exactitude factuelle et qualité pédagogique sur rubric ;
- conservation des anchors de traduction ;
- taux de fallback scene-coder et de repair non dégradé ;
- mêmes validateurs Pydantic et contrôles statiques ;
- promotion d’un modèle plus rapide seulement si l’intervalle de confiance respecte une marge de non-infériorité décidée avant le test.

### Proposition de seuils à ratifier

Les valeurs suivantes sont un point de départ, pas des normes déjà adoptées :

- pas de baisse de plus de 1 point de pourcentage du taux de succès first-pass ;
- pas de hausse de plus de 1 point du fallback scene-coder ;
- WER : hausse absolue ≤ 0,5 point ;
- MOS : aucune baisse statistiquement significative supérieure à 0,2/5 ;
- zéro nouvelle violation de résolution, FPS, freeze, loudness ou synchronisation ;
- gain de latence retenu seulement si visible sur P50 **et** P95.

## 13. Sources externes officielles

- [Remotion — Performance Tips](https://www.remotion.dev/docs/performance)
- [Remotion — Concurrency](https://www.remotion.dev/docs/terminology/concurrency)
- [Remotion — `renderMedia()`](https://www.remotion.dev/docs/renderer/render-media)
- [Remotion — Hardware accelerated encoding](https://www.remotion.dev/docs/hardware-acceleration)
- [Manim — Output and configuration](https://docs.manim.community/en/stable/tutorials/output_and_config.html)
- [Manim — Rendering deep dive](https://docs.manim.community/en/stable/guides/deep_dive.html)
- [vLLM — Automatic Prefix Caching](https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/)
- [vLLM — Speculative decoding](https://docs.vllm.ai/en/stable/features/spec_decode/)
- [OpenAI — Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenAI — Prompt caching](https://developers.openai.com/api/docs/guides/prompt-caching)
- [OpenAI — Latency optimization](https://developers.openai.com/api/docs/guides/latency-optimization)
- [Kubernetes — Schedule GPUs](https://kubernetes.io/docs/tasks/manage-gpus/scheduling-gpus/)
- [Kubernetes — Device Plugins](https://kubernetes.io/docs/concepts/extend-kubernetes/compute-storage-net/device-plugins/)
- [Kubernetes — Volumes](https://kubernetes.io/docs/concepts/storage/volumes/)
- [Kubernetes — Resource Managers](https://kubernetes.io/docs/concepts/workloads/resource-managers/)
- [Celery — Optimizing](https://docs.celeryq.dev/en/stable/userguide/optimizing.html)
- [MOSS-TTS v1.5 — Model card](https://huggingface.co/OpenMOSS-Team/MOSS-TTS-v1.5)
- [Resemble AI — Chatterbox](https://www.resemble.ai/learn/models/chatterbox)

## Conclusion

Le chemin le plus sûr vers une génération nettement plus rapide ne change ni la résolution, ni la voix, ni le contenu pédagogique. Il consiste à **maintenir les modèles chauds, isoler les ressources, chevaucher les branches indépendantes, rendre au niveau de la scène et réutiliser uniquement des artefacts exactement identiques**.

Sous réserve de validation sur le matériel bare-metal cible, le trio **TTS GPU persistant + TTS en parallèle du scene-coder + rendu Manim distribué** peut retirer environ **25–55 % du temps total** sur un job où TTS et rendu dominent. Cette plage n’est pas la somme naïve des gains individuels : elle suppose un chemin critique remesuré après chaque optimisation. Le cache de scène et le singleflight ajoutent surtout un gain massif sur réparations et doublons, tandis que le serving LLM et la concurrence Remotion apportent des gains plus modestes mais rapides à obtenir.

L’ordre recommandé reste donc : **mesurer, préchauffer, chevaucher, paralléliser par scène, puis cacher**. Les changements de modèle, la quantification et l’encodage matériel viennent ensuite, seulement comme expériences contrôlées de non-infériorité.
