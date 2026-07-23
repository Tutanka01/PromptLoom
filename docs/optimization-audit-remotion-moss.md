# Audit d’optimisation ciblé — Remotion + MOSS distant

**Projet :** PromptLoom

**Date de l’audit :** 23 juillet 2026

**Révision analysée :** `d70b0a674d5d` (`main`)

**Périmètre :** chemin de production Remotion, scene-coder et runtime React, MOSS-TTS distant, assemblage/QC associés et infrastructure bare-metal k3s.

**Contrat de qualité :** final 1920×1080 à 60 fps, narration et voix inchangées, synchronisation pilotée par l’audio réel, contrôles visuels et audio conservés.

**Nature de l’intervention :** analyse en lecture seule. Aucun fichier existant ni comportement du produit n’a été modifié ; ce rapport est le seul nouvel artefact.

## Résumé exécutif

Le chemin critique réel n’est pas celui qui dominait le premier audit. MOSS est déjà distant, persistant en mémoire et protégé par un cache WAV global inter-jobs. Le rendu de production est principalement Remotion. Il faut donc considérer comme **déjà acquis** le modèle TTS chaud, le CAS audio global, le navigateur téléchargé dans l’image, le rendu final unique d’un job réussi, les frames Remotion en JPEG et le mux final sans réencodage vidéo.

Les gains encore accessibles se concentrent sur cinq zones :

1. **régler la concurrence Remotion sur les CPU réellement alloués au pod**, car `75%` est calculé à partir des CPU visibles et peut ignorer un quota CFS k3s ;
2. **bundler et ouvrir Chrome une seule fois par vague de smoke checks**, puis rendre au plus deux stills en parallèle ;
3. **batcher réellement MOSS sur le GPU cible** et regrouper les segments de longueurs proches ;
4. **sortir les hits du cache MOSS de la file GPU**, aujourd’hui FIFO, puis télécharger les WAV dès qu’ils sont prêts ;
5. **réutiliser exactement les scènes Custom, attestations et checkpoints inchangés**, surtout lors des réparations.

Le pipeline présente aussi deux coûts inutiles et sûrs à retirer : les MP3 segmentaires ne sont consommés ni par le client ni par l’assemblage interne, et le WAV global est réencodé en MP3 avant d’être redécodé pour le mastering, le loudnorm et l’AAC final.

### Top 6 par ROI conditionnel

Le classement dépend du profil du job. Un job catalogue, un job avec plusieurs scènes Custom, un miss complet MOSS et une réparation ne partagent pas le même chemin critique.

| Rang | Optimisation | Gain bout en bout estimé | Éligibilité | Risque | Pourquoi maintenant |
|---:|---|---:|---|---|---|
| 1 | Concurrence Remotion entière, benchmarkée dans le pod réel | 5–25 % si `75%` suralloue ou sous-alloue ; 0 % si déjà optimal | Tous les rendus | Faible | Changement de configuration après mesure, sans changer une frame. |
| 2 | MOSS batch `1 → 2 → 4`, puis bucketing par budget de tokens | 6–28 % si le TTS représente 30–50 % du job et si le cache rate | Misses MOSS | Moyen | Le chemin vectorisé existe déjà, mais le défaut du dépôt vaut 1 et le vrai GPU n’est pas benchmarké. |
| 3 | Bundle smoke multi-compositions + navigateur partagé | 3–15 % d’un job Custom | Scènes Custom | Faible–moyen | Chaque still relance actuellement une CLI, un bundle et Chrome. |
| 4 | Fast-path CAS MOSS avant la FIFO GPU | <0–5 % à file vide ; 3–20 % sous file chargée, selon l’attente évitée | Hits MOSS | Faible–moyen | Le cache évite l’inférence mais pas aujourd’hui l’attente derrière un long job. |
| 5 | Cache exact TSX Custom + attestation `tsc`/still | 5–25 % d’une réparation Custom ; 70–95 % du coder sur hit | Réparations/duplications | Faible–moyen | Les scènes inchangées sont actuellement recodées et resmokées. |
| 6 | Chemin audio PCM direct jusqu’au mastering/AAC | 1–4 % typique ; 40–80 % du post-audio concerné | Tous les jobs | Très faible | Retire des encodages sans perte et peut légèrement améliorer la fidélité. |

Ces plages ne sont **pas cumulables**. Par exemple, un MOSS mieux batché réduit la portion encore masquable par le scene-coder ; supprimer les MP3 réduit la portion encore masquable par le téléchargement progressif.

### Décision recommandée

La trajectoire la plus sûre est :

1. corriger la mesure et figer le corpus 1080p60 ;
2. isoler les fichiers temporaires Remotion et durcir les artefacts audio avant d’ajouter de la concurrence ;
3. benchmarker la concurrence Remotion et MOSS `1/2/4` sur les pods réels ;
4. remplacer les CLI smoke successives par une API SSR avec bundle et navigateur partagés ;
5. ajouter les fast-paths et caches exacts ;
6. ne tester Chromium GPU et NVENC qu’après avoir séparé le temps de rendu des frames du temps d’encodage.

## 1. Méthode, limites et niveau de confiance

### 1.1 Sources inspectées

L’analyse repose principalement sur :

- `apps/video-api/src/video_api/pipeline/production.py`, pour l’ordre des étapes et les réparations ;
- `pipeline/remotion_materialize.py`, `pipeline/remotion_scene_coder.py` et `pipeline/engine.py` ;
- `apps/video-api/remotion/src`, le catalogue, `MainComposition.tsx`, `Root.tsx`, `remotion.config.ts`, `package.json` et `package-lock.json` ;
- `pipeline/voice.py` et le `generate_voice_en.py` réellement copié par le matérialiseur ;
- `apps/tts-server/src/tts_server/config.py`, `engine.py`, `jobs.py`, `cache.py` et l’API ;
- `pipeline/materialize.py`, `align.py`, `visual_review.py` et `verify.py` ;
- les Dockerfiles, Compose et la configuration disponible dans le dépôt ;
- la documentation officielle actuelle de Remotion, Kubernetes, K3s, NVIDIA, MOSS-TTS, FastAPI et FFmpeg.

### 1.2 Vérité de déploiement retenue

Le présent audit prend les informations fournies comme vérité de production :

- Remotion est le moteur principal ;
- le final attendu est 1080p60 ;
- la voix vient de MOSS distant ;
- le modèle MOSS est déjà chargé et persistant sur GPU ;
- le cache serveur est global et inter-jobs ;
- l’infrastructure est bare-metal k3s.

Les valeurs statiques du dépôt ne suffisent pas à prouver ces invariants : `config.py:84-100` garde d’autres défauts et ne force 60 fps que via l’environnement ou le mode `cinematic` (`production.py:99-114`). Le benchmark doit donc enregistrer les valeurs **effectives**, pas seulement lire le code.

### 1.3 Limites

- Aucun `report.json`, log de rendu de production ou historique de métriques n’est disponible localement.
- Aucun manifest Deployment/StatefulSet/Helm k3s, `ResourceQuota`, `LimitRange`, affinité ou limite CPU/mémoire déployée n’est présent dans le dépôt.
- Le batch MOSS effectif, la concurrence Remotion effective, le type de volume de `/data/jobs` et le placement GPU ne sont donc pas observables.
- Les gains bout en bout sont des estimations de chemin critique, pas des mesures.
- Les gains sous charge et les gains à vide sont séparés quand ils diffèrent.

Les formules de lecture sont :

```text
gain de chevauchement = min(T_A, T_B) / T_total
gain moyen d'un cache = taux_de_hit × part_de_phase × coût_évité
gain d'une accélération = part_de_phase × (1 - 1 / accélération_observée)
```

### 1.4 Confiance

| Type de constat | Confiance |
|---|---|
| Ordre des étapes, invalidations, commandes et formats actuels | Élevée : observés dans le code |
| Cause du rebundle/relaunch Chrome et de l’attente MOSS | Élevée |
| Compatibilité d’un cache exact ou du chemin PCM | Élevée si les clés et gates décrits sont respectés |
| Gain relatif d’une phase | Moyenne avant benchmark matériel |
| Gain bout en bout | Faible à moyenne avant télémétrie |
| NVENC, Chromium GPU, FlashAttention et batching MOSS | Faible à moyenne avant évaluation performance/qualité |

## 2. Correction du premier audit et chemin réel

### 2.1 Ce qui reste valide

| Recommandation antérieure | Verdict dans le contexte réel |
|---|---|
| Concurrence Remotion liée aux quotas | Valide et prioritaire, avec une nuance k3s importante sur les quotas CFS. |
| Bundle et navigateur chauds | Valide surtout pour les smoke checks Custom ; un bundle global n’est pas directement sûr pour des sources Custom et assets variables. |
| MOSS batch 2–4 | Valide, mais doit être benchmarké sur le vrai moteur et audité en qualité audio. |
| Téléchargement progressif | Valide, avec un gain plus faible sur LAN et seulement entre éléments effectivement publiés. |
| Suppression des MP3 intermédiaires | Valide et sûre si l’API MP3 externe est préservée ou dépréciée. |
| Scratch NVMe local | Valide uniquement si `/data/jobs` repose aujourd’hui sur un stockage plus lent. |
| NVENC | Expérience conditionnelle, impossible avec Remotion `4.0.400` sur Linux. |

Les recommandations consistant à créer un service MOSS persistant ou un CAS WAV global sont déjà réalisées. Elles ne doivent pas être comptées comme gains futurs.

### 2.2 Pipeline nominal observé

```text
blueprint validé
  ↓
assets + motion preflight
  ↓
matérialisation Remotion
  ↓
scene-coder Custom
  ├─ appels LLM parallèles par vague
  ├─ un tsc global
  └─ un `npx remotion still` séquentiel par candidat
  ↓
validation statique
  ↓
MOSS distant
  ├─ soumission des segments manquants
  ├─ attente du statut terminal du job
  ├─ téléchargement séquentiel des WAV
  └─ MP3/padding/concat audio
  ↓
alignement → cues → sous-titres → video.json
  ↓
copie entry/Custom/assets dans le projet Remotion partagé
  ↓
`npx remotion render` global 1920×1080×60
  ├─ bundle
  ├─ lancement Chrome
  ├─ rendu des frames
  └─ encodage x264 CRF 18
  ↓
mastering + loudnorm deux passes + AAC
  └─ vidéo copiée avec `-c:v copy`
  ↓
revue visuelle finale
  ↓
ffprobe + freezedetect + snapshots + QC audio
```

L’orchestration est séquentielle entre le scene-coder, MOSS, l’alignement, le rendu, l’assemblage, la revue et la vérification (`production.py:507-709`).

### 2.3 Optimisations déjà présentes à conserver

- Un job réussi ne rend le final qu’une fois ; la revue inspecte le fichier livré (`production.py:623-655`).
- Le navigateur Remotion est téléchargé pendant la construction de l’image.
- Les candidats Custom d’une vague partagent déjà un `tsc --noEmit`.
- Les appels LLM Custom sont déjà bornés et parallèles.
- Remotion utilise déjà JPEG pour les frames (`remotion.config.ts:3`).
- Le final utilise CRF 18 et x264 `faster`.
- Le mux final conserve la vidéo avec `-c:v copy`.
- Les WAV de segments inchangés sont conservés au sein du job.
- Le serveur MOSS conserve le modèle en mémoire et dispose d’un CAS WAV atomique.
- La langue explicite est transmise à MOSS, ce que recommande la carte v1.5.

### 2.4 Trois anomalies à traiter avant de comparer les gains

1. **Le 60 fps n’est pas garanti par le défaut du dépôt.** Le contrôle final vérifie le FPS attendu par l’engine ; si l’engine est configuré à 30, un 30 fps peut réussir (`config.py:87-100`, `production.py:99-114`, `verify.py:133-138`). Toute campagne doit forcer et enregistrer `60`.
2. **Les timings actuels sont incomplets.** `final_report["timings"]` est construit avant le passage à `completed`, et `_timings_from_marks()` ne mesure que les intervalles entre marques (`production.py:743-748`, `805-812`). La fin de `verify_final` manque et ce modèle ne représentera pas un DAG parallèle.
3. **La revue visuelle Remotion peut échouer sur les beats.** `_active_beat()` lit `beat.at`, `key`, `text_hint` et `visual_action`, alors que `RemotionBeat` expose `anchor` et `note` (`visual_review.py:149-165`, `schemas.py:653-663`). Ce défaut peut fausser un benchmark en transformant une revue en tentative de réparation.

## 3. Axe 1 — Optimisation Remotion pure

### 3.1 Concurrence : utiliser le quota réel, pas `75%` des CPU visibles

Le rendu passe `--concurrency="75%"` par défaut (`config.py:89-99`, `remotion_materialize.py:238-246`). Dans Remotion `4.0.400`, ce pourcentage est calculé à partir de `min(os.cpus().length, nproc)`. Il respecte donc un cpuset explicite, mais pas nécessairement une limite CPU k3s appliquée par quota CFS.

Exemple de risque :

```text
nœud : 32 CPU visibles
pod : limite CFS de 8 CPU, sans cpuset
Remotion 75% : jusqu'à 24 onglets calculés
effet : throttling, pression mémoire, changements de contexte et parfois OOM
```

La recommandation est de garder un seul rendu lourd par pod et de tester des entiers, par exemple `2, 4, 6, 8`, dans le pod réel avec `npx remotion benchmark`. L’entier retenu doit réserver du CPU à Node, au bundler et à ffmpeg.

Mesures minimales :

```text
nproc
/sys/fs/cgroup/cpu.max
/sys/fs/cgroup/cpuset.cpus.effective
/sys/fs/cgroup/memory.max
resolvedConcurrency
container_cpu_cfs_throttled_seconds_total
RSS, OOMKilled, frames/s, P50 et P95
```

Gain estimé : **10–35 % du rendu**, soit **5–25 % bout en bout** si le réglage actuel est mauvais ; **0 %** s’il est déjà optimal. Risque faible, complexité faible à moyenne, qualité identique.

### 3.2 Un bundle et un navigateur par vague de smoke

Le chemin actuel :

- écrit tous les candidats d’une vague ;
- lance un seul `tsc`, ce qui est sain ;
- boucle ensuite séquentiellement ;
- crée une entry distincte ;
- appelle `npx remotion still` pour chaque scène (`remotion_scene_coder.py:363-436`).

Chaque CLI rebundle, démarre un serveur et ouvre/ferme Chrome. L’API SSR Remotion permet au contraire :

1. une entry enregistrant `Smoke_<scene_key>` pour tous les candidats ;
2. un seul `bundle()` ;
3. un seul `openBrowser()` ;
4. deux `renderStill()` simultanés au maximum ;
5. la fermeture ou le recyclage du navigateur selon TTL, RSS et nombre de jobs.

Remotion documente explicitement qu’appeler `bundle()` pour chaque vidéo est un anti-pattern et que réutiliser un navigateur évite les coûts d’ouverture/fermeture.
Le cache Webpack est déjà activé par défaut : le gain attendu vient surtout de la suppression des invocations et navigateurs répétés, pas de la disparition de tout coût de compilation.

Gain estimé :

- bundle/navigateur partagés : **35–70 % de la phase smoke**, **2–12 % d’un job Custom** ;
- pool de deux stills après mutualisation : **30–50 % des stills restants**, **1–6 % d’un job Custom**.

Le pool doit rester borné. Deux CLI indépendantes en parallèle doubleraient justement les bundles et navigateurs que l’on cherche à supprimer.

### 3.3 Préflight adaptatif sans toucher au final

Le smoke actuel rend une seule frame à 1920×1080, frame 75, et ne réalise pas d’analyse de lisibilité : il vérifie surtout que la scène compile, monte et rend sans erreur (`remotion_scene_coder.py:439-449`).

`scale=0.5` conserve le canevas logique 1920×1080 et les mêmes calculs de layout, imports, hooks, Shiki, KaTeX et `delayRender`; seule l’image sortie mesure 960×540. Il peut donc être utilisé pour le smoke technique, à condition de conserver :

- au moins un still pleine résolution pour le candidat accepté si un gate pixel/lisibilité est ajouté ;
- le chemin pleine résolution pour toute scène Canvas/WebGL dont le backing bitmap dépend du device scale ;
- la revue du final 1080p60 ;
- les contrôles spécifiques aux petits textes, formules et overflow.

Diminuer le FPS du still ne sert à rien : une seule frame est rendue et l’état temporel testé changerait.

Gain estimé : **5–25 % de la phase smoke actuelle**, **0–3 % bout en bout**. Risque faible, complexité faible, final inchangé.

### 3.4 Hotspots du catalogue et du runtime

Le runtime contient plusieurs coûts par frame qui méritent un profilage avant toute extension matérielle :

- `MainComposition` rend un `AmbientBackground` global (`MainComposition.tsx:170`) ;
- de nombreuses scènes palette via `Shell` en rendent également un (`scenes/data/scenes.tsx:54`) ;
- chaque fond construit environ 608 cercles SVG animés et un gradient radial par frame (`AmbientBackground.tsx:22-43`) ;
- `MathFormula` appelle `katex.renderToString()` pendant le rendu React (`MathFormula.tsx:40`) ;
- `Plot` rééchantillonne les séries et reconstruit grilles/paths à chaque frame ;
- gradients, blur, `box-shadow`, `text-shadow` et filtres sont nombreux alors que `swangle` force un backend logiciel (`remotion.config.ts:8`).

Le premier levier est de conserver **un seul fond persistant**, avec l’accent de la scène active et une parité précise aux transitions. Les géométries statiques de KaTeX et Plot peuvent être mémorisées par dépendances exactes ; seules les progressions réellement animées doivent être recalculées.

Gain estimé : **5–20 % du frame rendering**, **3–12 % bout en bout si Chrome domine**. Risque faible à moyen pour la mémorisation, moyen pour la déduplication du fond ; complexité moyenne ; qualité compatible après snapshots et pixel-diffs tolérants.

Pour les jobs contenant du footage, le runtime utilise `OffthreadVideo`. La documentation Remotion actuelle préfère `<Video>` de `@remotion/media`, mais cette migration exige une mise à niveau cohérente des paquets et une validation de seek, loop et frames de frontière. Gain potentiel : **10–30 % des frames footage**, **0–10 % du job selon leur part** ; priorité faible hors vidéos riches en média.

### 3.5 Chromium GPU et NVENC sont deux expériences distinctes

**Chromium GPU** accélère la production des frames contenant gradients, transforms, ombres, blur, Canvas ou vidéo. Le runtime force actuellement `swangle`, donc un backend logiciel. Un test avec un backend GPU réel sur un nœud de rendu dédié peut viser **10–40 % du frame rendering**, soit **5–25 % d’un job éligible**. Le risque est moyen à élevé : pilotes, backend GL, stabilité headless et parité pixel doivent être validés.

**NVENC** n’accélère que l’encodage des frames déjà produites. Le lockfile installe Remotion `4.0.400`, tandis que NVENC Linux/Windows exige au moins `4.0.484`. Une mise à niveau coordonnée de tous les paquets Remotion est donc préalable.

Le final actuel utilise CRF 18. Les encodeurs matériels Remotion n’acceptent pas CRF ; il faut sélectionner un bitrate. Le conseil générique de 8 Mbit/s pour du Full HD ne constitue pas une garantie pour du 1080p60 avec petits textes, formules et gradients.

Décision :

- mesurer `renderedDoneIn` et `encodedDoneIn` via `renderMedia()` ;
- ignorer NVENC si l’encodage représente moins de 10–15 % du rendu ;
- utiliser un GPU distinct de MOSS ;
- comparer bitrate, taille, VMAF/SSIM, OCR/lisibilité et inspection humaine ;
- exiger l’accélération pendant le benchmark pour éviter un fallback silencieux.

Gain potentiel : **2–5× sur l’encodage seul**, typiquement **2–10 % bout en bout**. Risque moyen à élevé, complexité moyenne à élevée, qualité conditionnelle à la non-infériorité.

## 4. Axe 2 — Pipeline Remotion end-to-end

### 4.1 DAG sûr : scene-coder et MOSS en parallèle, seulement pour Custom

Après matérialisation, le scene-coder/smoke et MOSS utilisent des ressources différentes et ne dépendent pas l’un de l’autre :

```text
matérialisation
  ├── Custom LLM → scan statique → tsc → bundle/stills ──┐
  └── MOSS distant → WAV validés → durées/agrégat ───────┤
                                                         ↓
                                                  barrière
                                                         ↓
                                      alignement → cues/video.json
                                                         ↓
                                              rendu Remotion
```

Contraintes :

- pour une vidéo 100 % catalogue, `generate_custom_scenes()` retourne immédiatement ; le gain de cette branche est donc **0 %** (`remotion_scene_coder.py:238-243`) ;
- les validations peu coûteuses du blueprint et des sources matérialisées doivent précéder le fork, puis la validation finale du code généré reste obligatoire ;
- la session SQLAlchemy ne doit pas être partagée entre threads ; les progrès doivent revenir par une file ou un orchestrateur ;
- les manifests audio doivent être publiés atomiquement ;
- une erreur statique doit annuler MOSS à la prochaine frontière de microbatch ;
- le join précède l’alignement/cues et le rendu, car les durées audio réelles pilotent la scène.

Gain estimé : **3–15 % bout en bout sur un job Custom avec MOSS chaud**, parfois davantage si les deux branches sont longues et réellement isolées ; **0 % sur un job catalogue**. Risque moyen, complexité moyenne, qualité identique.

### 4.2 Cache exact du code Custom et des attestations

À chaque tentative, le matérialiseur supprime `remotion_scenes/`, et les scènes Custom sont régénérées, typecheckées et smokées même si elles n’ont pas changé (`remotion_materialize.py:274-294`, `remotion_scene_coder.py:238-341`).

Deux clés distinctes sont nécessaires.

Clé de code :

```text
JSON canonique de la scène + contexte blueprint effectivement injecté
+ modèle et paramètres de génération
+ hashes des prompts, skill et guidance
+ version du normaliseur et du schéma
```

Clé d’attestation :

```text
hash TSX
+ package-lock et hashes runtime/catalogue/lib
+ TypeScript, Remotion, Chrome, polices et image
+ props, digests des assets, frame, échelle et paramètres du still
```

Le scan statique peu coûteux doit toujours être rejoué. Une attestation n’est réutilisable que sous digest runtime exact.

Gain estimé : **70–95 % du scene-coder sur hit**, **5–25 % d’une réparation Custom**, et environ **1–8 % de moyenne** selon le taux de réparation. Risque faible à moyen, complexité moyenne, qualité identique sous clé exhaustive.

### 4.3 Reprendre au dernier checkpoint valide

La boucle de tentative attrape largement les erreurs puis peut relancer une réparation de blueprint. Une panne Chrome, OOM, erreur ffmpeg ou indisponibilité transitoire peut ainsi modifier du contenu valide et invalider code, assets, alignement et rendu (`production.py:404-445`, `751-778`).

La reprise doit distinguer :

- rejet éditorial ou visuel : réparation ciblée ;
- source invalide : réparation de la scène concernée ;
- bundle/Chrome/ffmpeg : reprise avec mêmes sources, audio et `video.json` ;
- assemblage : reprise à l’assemblage ;
- MOSS distant : retry explicite sans changer voix ni narration.

Gain estimé : **50–90 % d’une tentative éligible**, soit **2–15 % à l’échelle de la flotte** selon les échecs. Risque moyen, complexité moyenne à élevée, qualité compatible et contenu mieux préservé.

### 4.4 Isoler `tsc`, les sources et `publicDir` avant la concurrence

Deux contaminations inter-jobs sont possibles :

1. `tsc --noEmit` utilise un `tsconfig` global dont `include` couvre tout `src`; il peut voir les candidats temporaires d’un autre job et leur attribuer des erreurs ;
2. les jobs copient leurs médias sous le même `remotion/public/job-assets/<id>`, puis `bundle()` copie par défaut tout `public/`. Des jobs concurrents peuvent donc copier les footages des autres, gonfler les bundles et subir des nettoyages concurrents.

Il faut un `tsconfig` par vague et un `publicDir` par job, ou des blobs immuables servis hors bundle. C’est un prérequis de correction avant d’augmenter la concurrence de jobs ou de stills.

Une fois isolé, un cache TypeScript incrémental lié au digest runtime peut économiser **30–70 % du typecheck chaud**, soit **1–5 % d’un job Custom**. Risque faible à moyen, complexité moyenne, qualité identique et stabilité sous charge améliorée.

### 4.5 Bundler tôt et réutiliser le bundle accepté

Le bundle validé pour les stills peut, si l’entry enregistre aussi la composition finale, être réutilisé avec les `inputProps` produits après MOSS et alignement. Le bundling peut commencer dès que le code Custom est validé, en parallèle du reste de la branche audio.

Un bundle global par version n’est cependant sûr que pour le runtime palette dont les sources et la résolution des assets sont immuables. Pour Custom, la clé doit couvrir toutes les sources. Pour les médias, `publicDir` doit être isolé ou les URLs immuables.

Gain estimé : **70–95 % du coût de démarrage bundle**, **1–8 % bout en bout** sur une vidéo longue et davantage sur une courte. Risque moyen, complexité moyenne à élevée, qualité identique.

### 4.6 Préparer l’audio final pendant le rendu

Le mastering et la mesure/application loudnorm ne dépendent pas des pixels. Une fois le WAV agrégé et la durée cible connus, cette branche peut produire l’audio masterisé en parallèle de l’alignement et du rendu. Le mux final conserve ensuite la vidéo et ajoute un AAC encodé une seule fois.

Il faut conserver exactement :

- la même chaîne de mastering ;
- le loudnorm deux passes et son fallback ;
- le même objectif LUFS/true peak ;
- le padding calculé sur la durée exacte en frames ;
- un seul encodage AAC final.

Gain estimé : **60–90 % de la phase assemblage**, **1–6 % bout en bout**. Risque moyen à cause des arrondis durée/frame, complexité moyenne, qualité compatible sous comparaison échantillon/durée.

### 4.7 Mutualiser la revue et les contrôles

La revue extrait trois PNG par scène via des processus ffmpeg successifs (`visual_review.py:272-303`). La vérification relance ensuite ffprobe, un décodage complet pour `freezedetect`, plusieurs snapshots et le QC audio.

Une optimisation sûre consiste à :

- extraire tous les timestamps demandés dans une ou quelques passes ffmpeg ;
- réutiliser les snapshots communs à la revue et à la vérification ;
- lancer le QC audio en parallèle de l’appel vision ;
- joindre tous les résultats avant publication ;
- conserver les mêmes timestamps, seuils, images et décision fail-closed.

Gain estimé : **30–70 % du post-rendu**, **1–8 % bout en bout**. Risque faible à moyen, complexité moyenne, qualité identique.

### 4.8 Cache de rendu : entier d’abord, frames ensuite

Le rendu final est une composition globale : fond animé persistant, sous-titres top-level et transitions de frontière (`MainComposition.tsx:144-200`). Un cache de MP4 indépendants par scène casserait potentiellement :

- le frame absolu du fond ;
- les transitions ;
- les sous-titres ;
- les GOP/timebases ;
- l’homogénéité d’encodage.

Deux niveaux sont raisonnables :

1. **CAS du silent MP4 ou final exact**, avec singleflight, clé couvrant bundle, `video.json`, assets, runtime, Chrome/GL, résolution, 60 fps et encodeur. Gain : **90–98 % du rendu sur doublon**, **30–75 % bout en bout du doublon**.
2. **Cache de frames/plages globales**, puis encodage final unique. Il conserve le frame absolu et invalide toutes les plages aval si une durée antérieure change. Gain : **30–80 % d’un rerender réparé**, environ **2–15 % de moyenne** si les réparations sont fréquentes ; risque et complexité élevés.

Le second niveau est une phase avancée, pas un quick win.

## 5. Axe 3 — MOSS distant

### 5.1 État réel

Le client :

- conserve les WAV locaux valides d’une tentative ;
- soumet uniquement les segments manquants ;
- envoie tous les manquants dans un job distant ;
- attend le statut terminal ;
- télécharge ensuite les WAV séquentiellement ;
- encode des MP3 par segment et un MP3 global (`generate_voice_en.py:513-653`).

Le serveur :

- charge le modèle une fois ;
- possède un seul worker FIFO ;
- sert les jobs séquentiellement ;
- dispose d’un CAS global ;
- ne consulte ce CAS qu’une fois le job sorti de la FIFO ;
- batch réellement via `model.generate()`, mais avec une taille par défaut de 1 (`tts_server/config.py:38-43`, `jobs.py:201-323`, `engine.py:280-318`).

### 5.2 Batch `1/2/4` et regroupement par longueur

Le code vectorisé existe. Un batch prend le plus grand budget `max_new_tokens` parmi ses segments ; des longueurs très divergentes dégradent donc l’efficacité (`engine.py:307-318`).

Plan :

1. benchmarker `1`, `2`, puis `4` sans modifier modèle, dtype, référence ou paramètres ;
2. relever temps GPU, secondes audio, RTF, VRAM, token caps et erreurs ;
3. grouper les misses par budget `estimate_new_tokens()`, pas seulement par caractères ;
4. restaurer l’ordre éditorial lors de l’écriture des résultats ;
5. tester séparément courts, longs et lots mixtes.

Gain estimé : **20–55 % de la synthèse**, environ **6–28 % bout en bout** si le TTS représente 30–50 % du job. Risque moyen : OOM, troncature et tirages stochastiques différents selon le batch. Complexité faible pour `1/2/4`, moyenne pour le bucketing. Qualité conditionnelle à WER, similarité locuteur, MOS/prosodie et absence de token cap.

Une référence de voix approuvée déjà utilisée en production supprime la barrière du premier segment, aujourd’hui généré seul quand aucune référence n’est fournie (`jobs.py:228-239`). Introduire une nouvelle référence qui changerait le timbre n’est pas une optimisation neutre.

### 5.3 Fast-path cache avant la file GPU

Les hits sont actuellement matérialisés dans `_process()`, après l’attente dans la FIFO. Un job 100 % cache-hit peut donc rester bloqué derrière une longue synthèse malgré l’absence de calcul GPU.

Avec une référence explicite, toutes les empreintes sont connues à l’admission. Le serveur peut :

- matérialiser immédiatement les hits ;
- publier leurs `wav_url` ;
- n’envoyer que les misses au scheduler GPU.

Sans référence explicite, le premier segment reste une barrière si son ancre n’existe pas encore.

Gain estimé :

- à file vide, environ **0–2 s** de dequeue/poll évitées, souvent **moins de 0–5 % bout en bout** ;
- sous file chargée, **70–99 % de l’attente TTS** du hit peut disparaître ;
- dans ce second cas, le gain peut atteindre **3–20 % bout en bout**, voire davantage si l’attente dominait le P95.

Risque faible à moyen, complexité moyenne, qualité identique car les mêmes WAV sont copiés.

### 5.4 Téléchargement anticipé et publication atomique

L’API expose `wav_url` dès qu’un segment est `done` (`tts_server/jobs.py:172-198`). Le client attend pourtant le statut terminal avant tout téléchargement (`generate_voice_en.py:574-598`).

Le corps HTTP est déjà streamé par `FileResponse` côté serveur et `shutil.copyfileobj()` côté client. Le levier est donc le **moment de démarrage** du transfert, pas un remplacement cosmétique par un autre type de réponse.

À chaque poll, il peut télécharger les nouveaux segments terminés, avec deux à quatre transferts LAN bornés. Le gain intervient surtout entre microbatches et pour les hits ; tous les éléments d’un même batch ne sont publiés qu’après la fin de ce batch.

Le téléchargement actuel écrit directement dans `<key>.wav`. Une coupure peut laisser un artefact partiel. Le garde MP3 actuel en détecte normalement une partie lors du retry, mais un WAV tronqué encore décodable peut passer, et le futur chemin WAV-only retirerait ce garde indirect. Le protocole doit donc être :

```text
<key>.wav.part
  → vérifier RIFF/WAVE, PCM16, canaux, sample rate, frames et taille/hash
  → comparer la durée serveur comme contrôle, pas comme source exacte
  → rename atomique vers <key>.wav
```

Les manifests globaux ne sont publiés qu’après le statut terminal réussi. Une erreur MOSS doit toujours faire échouer clairement la vidéo.

Gain estimé : **2–10 % de la chaîne TTS/audio**, généralement **moins de 1–4 % bout en bout sur LAN**. Risque faible après atomicité, complexité moyenne, qualité identique. L’atomicité seule n’accélère pas le nominal mais constitue un garde-fou obligatoire.

### 5.5 Supprimer les MP3 redondants

Le chemin actuel encode :

1. un MP3 par segment côté serveur ;
2. un autre MP3 par segment côté client ;
3. un MP3 global depuis le WAV agrégé ;
4. puis décode ce MP3 pour mastering/loudnorm et encode l’AAC final.

Le client ne télécharge jamais les MP3 serveur. Aucun consommateur interne des MP3 segmentaires n’a été trouvé. Le chemin recommandé est :

```text
WAV PCM16 MOSS
  → padding/concat PCM
  → voiceover_en.wav
  → mastering + loudnorm deux passes
  → AAC final 192 kb/s
```

Les MP3 de l’API TTS peuvent rester disponibles par encodage à la demande ou pendant une période de dépréciation si un consommateur externe existe.

Gain estimé : **40–80 % du post-audio concerné**, **1–4 % bout en bout**. Risque très faible, complexité faible à moyenne, qualité compatible et potentiellement légèrement meilleure grâce à une génération avec perte retirée.

### 5.6 Agrégats audio et cache

Le client lance aujourd’hui `ffprobe` et ffmpeg pour chaque segment, produit un WAV paddé par scène, concatène puis encode le global. Une seule chaîne PCM peut effectuer padding et concaténation, avec un cache d’agrégat séparé du cache de synthèse.

Les clés doivent séparer :

- WAV brut : voix, modèle et texte ;
- padding : WAV brut + padding et format ;
- agrégat : liste ordonnée des WAV/paddings ;
- audio masterisé : agrégat + chaîne mastering/loudnorm + durée cible.

Gain estimé : **50–90 % du post-audio froid**, **90–99 % sur hit d’agrégat**, soit **1–5 % bout en bout**. Risque faible à moyen sur les arrondis échantillons/frames, complexité moyenne, qualité compatible après comparaison exacte.

### 5.7 Durcir les clés avant d’augmenter le taux de hit

Le CAS serveur couvre le modèle nominal, la langue, le texte normalisé et le hash de référence (`tts_server/cache.py:33-37`). Il ne couvre pas :

- le commit Hugging Face résolu ;
- le code distant/processor ;
- le digest d’image et les versions Torch/Transformers ;
- le dtype et le backend d’attention ;
- la configuration de génération ;
- la politique de budget de tokens.

`from_pretrained()` est appelé sans `revision`, donc une branche de modèle peut changer. La signature locale contient le chemin de référence mais pas le contenu ; remplacer un WAV de banque au même chemin peut réutiliser de vieux fichiers. Elle inclut en revanche le tail padding, qui ne devrait pas invalider un WAV brut.

Avant un nouveau cache ou un fast-path agressif, définir un `synthesis_profile_id` :

```text
repo modèle + commit résolu + remote code
+ digest image + versions runtime
+ dtype + attention + paramètres de génération
+ langue + message exact sérialisé
+ SHA-256 de la référence
+ format audio + version du générateur
```

Gain direct : **0 %**. Risque faible, complexité moyenne, qualité renforcée ; c’est un prérequis à la sûreté des caches.

### 5.8 Optimisations MOSS secondaires

- **Scheduler microbatch round-robin entre jobs compatibles :** 10–35 % de débit sous charge, P95 amélioré de 15–50 %, gain nul à vide ; risque moyen, complexité élevée, qualité à revalider car le groupement change.
- **Annulation coopérative à la frontière d’un microbatch :** 0 % nominal, 10–100 % du travail restant économisé sur annulation/timeout ; risque faible à moyen, complexité moyenne, qualité inchangée.
- **Cache L1 côté worker :** 60–95 % de la phase client sur hit local, mais probablement moins de 1–3 % bout en bout sur LAN après fast-path serveur ; risque de clé périmée et cache par nœud, priorité faible.
- **FlashAttention 2 :** la carte MOSS v1.5 l’annonce comme option vitesse/mémoire. Estimation 5–25 % de la synthèse, 1–10 % bout en bout ; risque moyen et qualité numérique à valider.
- **Hash de référence calculé une seule fois par job :** 80–95 % de ce sous-coût, moins de 0,1–1 % du total ; correct mais non prioritaire.

## 6. Axe 4 — Infrastructure bare-metal k3s

### 6.1 Ce qui est connu et ce qui ne l’est pas

Le dépôt montre des services distincts pour le worker vidéo et MOSS, mais ne contient pas les manifests k3s déployés. Il est donc impossible d’affirmer :

- si le worker dispose de CPU entiers ou d’un simple quota CFS ;
- si `/data/jobs` est local, NFS, Longhorn ou un autre CSI ;
- si le pod MOSS demande `nvidia.com/gpu: 1` ;
- si les nœuds sont taintés/labellisés ;
- si les images sont préchargées ;
- si le CAS MOSS réside sur un volume local ou réseau.

Les seuls faits d’infrastructure observables sont plus modestes :

- Compose monte un espace `/data/jobs` commun à l’API et au worker ;
- le worker Celery Compose a une concurrence de 1 et aucune limite CPU, mémoire ou stockage déclarée ;
- le Compose MOSS monte un unique `/data` pour les jobs, le CAS et les données de modèle, et réserve tous les GPU visibles ;
- `/healthz` reste non prêt jusqu’au chargement du modèle ;
- un redémarrage marque les jobs MOSS en vol comme échoués.

Les recommandations ci-dessous décrivent une cible à valider, pas l’état actuel du cluster.

### 6.2 Topologie cible

```text
file/orchestrateur vidéo
  ├── pods Remotion CPU
  │     ├── 1 rendu lourd par pod
  │     ├── CPU/mémoire garantis
  │     ├── scratch NVMe local
  │     └── bundle/Chrome chauds et isolés
  │
  └── service MOSS
        ├── 1 pod chaud par GPU physique
        ├── nvidia.com/gpu: 1
        ├── modèle + référence approuvée
        ├── CAS WAV persistant
        └── microbatch scheduler borné

stockage durable
  ├── état Postgres
  ├── rapports et MP4 finaux
  └── checkpoints/CAS nécessaires à la reprise
```

Un éventuel pod Chromium GPU/NVENC doit cibler un autre GPU ou une partition matériellement isolée. Le GPU MOSS ne doit pas être partagé par défaut avec le rendu : la contention rendrait les latences TTS et Remotion moins prévisibles.

### 6.3 Scratch NVMe local et promotion durable

Les bundles, sources temporaires, stills, frames, WAV de travail et fichiers ffmpeg sont des données de scratch. Si `/data/jobs` repose aujourd’hui sur un volume réseau, ils doivent être placés sur un NVMe local :

- `emptyDir` seulement si le stockage éphémère kubelet est réellement sur ce NVMe ;
- sinon un Local PersistentVolume avec `nodeAffinity` et `WaitForFirstConsumer` ;
- `requests`/`limits` d’`ephemeral-storage` et `sizeLimit` explicites ;
- promotion atomique du MP4 final, du rapport et des checkpoints vers le stockage durable.

Un `emptyDir` est perdu si le pod est supprimé ou déplacé. Cette architecture exige donc une reprise depuis les checkpoints durables, pas une supposition de durabilité locale.

Gain estimé :

- **5–20 % bout en bout** si le chemin actuel est limité par un PVC réseau ;
- **0–5 %** s’il est déjà local et rapide ;
- amélioration P95 plus forte sur footage et bundles volumineux.

Risque moyen, complexité moyenne à élevée, qualité identique.

### 6.4 Ressources CPU/mémoire stables pour Remotion

Deux options :

1. pod Guaranteed avec requêtes=limites, CPU entier et CPU Manager `static`, donnant un cpuset exclusif ;
2. quota CFS classique, mais concurrence Remotion fournie comme entier dérivé de la limite et benchmarkée sous throttling réel.

Le premier choix réduit migrations et contention de cache CPU, mais nécessite une configuration kubelet et une réservation système. Dans les deux cas :

- un seul rendu lourd par pod ;
- limite mémoire mesurée avec Chrome, bundler et footage ;
- marge pour ffmpeg ;
- `ephemeral-storage` dimensionné ;
- pas de concurrence Celery supérieure à la capacité du pod.

Gain estimé : **0–15 % à vide**, **10–30 % et surtout un meilleur P95 sous contention**. Risque faible, complexité moyenne, qualité identique.

### 6.5 Placement GPU MOSS

K3s détecte le runtime NVIDIA s’il est installé ; le pod doit demander le runtime approprié et `nvidia.com/gpu: 1`. L’extended resource GPU empêche l’overcommit involontaire. Ajouter :

- label et taint pour les nœuds GPU ;
- affinité du pod MOSS ;
- `startupProbe` assez longue pour le chargement ;
- `readinessProbe` seulement après disponibilité réelle du modèle ;
- au moins un replica fixe, sans autoscale-to-zero, puisque le contexte exige un service chaud ;
- métriques DCGM : GPU util, mémoire, encodeur, erreurs Xid et température.

Le modèle chaud est déjà acquis : le pré-warming n’améliore pas le steady-state, mais protège le P95 après redémarrage.

Gain direct à vide : **0 %**. Sous contention évitée, il peut prévenir **10–40 % de régression P95**. Risque faible, complexité moyenne, qualité identique.

Le time-slicing NVIDIA n’est pas une isolation suffisante entre MOSS et un rendu : il ne fournit ni isolation mémoire ni isolation de panne. Si un seul GPU physique est disponible, il doit rester attribué à MOSS ; Chromium GPU et NVENC restent alors désactivés ou planifiés dans une fenêtre sans synthèse, après benchmark explicite.

### 6.6 Pré-pull d’image, bundle et navigateur

Le navigateur binaire est déjà inclus dans l’image ; il ne faut pas recommander un téléchargement à chaque job. Les coûts froids restants sont le pull d’image, l’ouverture de Chrome, le bundle et le chargement du modèle après redémarrage.

- K3s peut pré-importer les images dans containerd via `/var/lib/rancher/k3s/agent/images`.
- Une image de rendu dédiée peut éviter de tirer des dépendances inutiles sur les nœuds Remotion.
- Le bundle palette immuable peut être construit par image digest ou init container.
- Un daemon de rendu peut garder Chrome ouvert avec TTL, plafond RSS, recyclage après N jobs et healthcheck.
- Un bundle Custom ne peut être préchauffé globalement qu’avec une clé exacte de sources.
- Le pod MOSS peut précharger le modèle puis passer Ready ; son cache modèle doit survivre aux redémarrages selon la politique du nœud.

Gain : **30–90 % du cold start**, **0 % en steady-state chaud**. Risque faible à moyen, complexité moyenne, qualité identique.

### 6.7 Files et capacité

Le service MOSS n’exécute qu’un job GPU à la fois aujourd’hui, même s’il batche les segments d’un job. Sous charge, une file dédiée et un scheduler par microbatch permettent de choisir explicitement entre :

- latence d’un job ;
- débit de la flotte ;
- équité entre jobs courts et longs.

Pour Remotion, répliquer les pods CPU sur les nœuds NVMe est préférable à lancer plusieurs rendus dans le même quota. L’orchestrateur doit limiter les admissions à la capacité réelle et publier :

- profondeur/âge de file ;
- temps d’attente et de service ;
- cache-hit avant/après file ;
- CPU throttlé, RSS, I/O et espace scratch ;
- GPU, VRAM, RTF et taille de batch ;
- durée bundle, frame rendering et encodage séparées.

Gain estimé : **10–40 % de débit sous charge** et **15–50 % de P95** selon la contention ; **0 % à vide**. Risque moyen, complexité élevée, qualité compatible sous limites stables.

### 6.8 Séparer le stockage MOSS et rendre les arrêts explicites

Le volume MOSS ne devrait pas confondre trois durabilités :

- poids Hugging Face et cache de modèle : reconstructibles, idéalement NVMe local ;
- jobs et fichiers de service : temporaires ;
- CAS WAV inter-jobs : persistant et cohérent, local au GPU si ce placement est stable, partagé ou répliqué seulement si plusieurs GPU servent réellement la même flotte.

Si `/data` est aujourd’hui réseau, séparer le cache modèle et le travail temporaire peut retirer **10–50 % du cold start ou d’un cache-hit local**, mais seulement **0–5 % du steady-state bout en bout** une fois le modèle chaud. Risque moyen de perte de localité au rescheduling, complexité moyenne, audio identique.

Un `startupProbe` et un `readinessProbe` sur l’état réel du modèle empêchent le trafic prématuré. Un PodDisruptionBudget ne sauve cependant pas un job en cours : il faut aussi arrêter les admissions, drainer jusqu’à la frontière d’un microbatch, puis laisser un `terminationGracePeriodSeconds` supérieur au batch maximal. Cela n’accélère pas un job nominal, mais peut éviter **jusqu’à 100 % du travail restant** lors d’un drain volontaire. Risque moyen, complexité moyenne, qualité identique.

Avec plusieurs nœuds CPU, un pod Remotion résident par allocation de ressources et une concurrence Celery de 1 permettent un scale horizontal. Le débit peut alors augmenter de **50–200 %** selon le nombre de nœuds et le goulot aval, sans réduire la latence d’un job isolé. Ce chiffre mesure la capacité de flotte, pas un speedup mono-job.

## 7. Matrice consolidée gains / risques / complexité

Les gains sont conditionnels et non cumulables. « E2E » signifie bout en bout du job éligible.

| ID | Optimisation | Gain de phase estimé | Gain E2E estimé | Risque | Complexité | Compatible qualité actuelle ? |
|---|---|---:|---:|---|---|---|
| R1 | Concurrence Remotion entière liée au pod | 10–35 % rendu si mal réglé | 5–25 % ; 0 % si déjà optimal | Faible | Faible–moyenne | Oui |
| R2 | Bundle + navigateur uniques par vague smoke | 35–70 % smoke | 2–12 % Custom | Faible–moyen | Moyenne | Oui, mêmes gates |
| R3 | Deux `renderStill()` simultanés sur bundle chaud | 30–50 % des stills restants | 1–6 % Custom | Moyen, RAM | Faible–moyenne après R2 | Oui |
| R4 | Smoke `scale=0.5`, final inchangé | 5–25 % smoke | 0–3 % | Faible | Faible | Oui avec gate full-res conservé |
| R5 | Un fond global + géométrie statique mémorisée | 5–20 % frame rendering | 3–12 % si Chrome domine | Faible–moyen | Moyenne | Oui après parité visuelle |
| R6 | Chromium GPU sur nœud dédié | 10–40 % frame rendering | 5–25 % éligible | Moyen–élevé | Élevée | Conditionnelle |
| R7 | Migration footage vers `@remotion/media` | 10–30 % frames footage | 0–10 % | Moyen | Moyenne | Conditionnelle au seek/loop |
| R8 | NVENC après upgrade Remotion | 2–5× encodage seul | 2–10 % typique | Moyen–élevé | Moyenne–élevée | Conditionnelle au bitrate |
| E1 | Scene-coder/smoke en parallèle de MOSS | économie `min(A,B)` | 3–15 % Custom ; 0 % catalogue | Moyen | Moyenne | Oui |
| E2 | Cache exact TSX + attestation | 70–95 % coder sur hit | 5–25 % réparation Custom | Faible–moyen | Moyenne | Oui sous clé exhaustive |
| E3 | Reprise au dernier checkpoint valide | 50–90 % tentative éligible | 2–15 % flotte | Moyen | Moyenne–élevée | Oui |
| E4 | `tsc`/`publicDir` isolés + cache incrémental | 30–70 % typecheck chaud | 1–5 % Custom | Faible–moyen | Moyenne | Oui, fail-closed |
| E5 | Bundle accepté réutilisé et lancé tôt | 70–95 % coût bundle | 1–8 % | Moyen | Moyenne–élevée | Oui |
| E6 | Mastering/loudnorm en parallèle du rendu | 60–90 % assemblage | 1–6 % | Moyen | Moyenne | Oui si même chaîne |
| E7 | Extractions/QC mutualisés et parallèles | 30–70 % post-rendu | 1–8 % | Faible–moyen | Moyenne | Oui, mêmes seuils |
| E8 | CAS silent/final exact + singleflight | 90–98 % rendu sur hit | 30–75 % doublon | Faible–moyen | Moyenne | Oui sous digest exact |
| E9 | Cache de frames/plages globales | 30–80 % rerender réparé | 2–15 % si réparations fréquentes | Élevé | Élevée | Conditionnelle |
| M0 | `synthesis_profile_id` + clés versionnées | 0 % direct | 0 % | Faible | Moyenne | Oui, prérequis |
| M1 | MOSS batch `1/2/4` + bucketing | 20–55 % synthèse | 6–28 % si TTS=30–50 % | Moyen | Faible–moyenne | Conditionnelle à l’audio |
| M2 | Fast-path CAS avant FIFO GPU | 0–2 s à vide ; attente −70–99 % sous file | <0–5 % à vide ; 3–20 % sous charge | Faible–moyen | Moyenne | Oui, WAV identique |
| M3 | Téléchargement progressif atomique | 2–10 % chaîne audio | <1–4 % sur LAN | Faible | Moyenne | Oui |
| M4 | Supprimer MP3 segmentaires et global | 40–80 % post-audio concerné | 1–4 % | Très faible | Faible–moyenne | Oui, fidélité non dégradée |
| M5 | Padding/concat PCM + cache agrégat | 50–90 % post-audio ; 90–99 % sur hit | 1–5 % | Faible–moyen | Moyenne | Oui après contrôle samples |
| M6 | Scheduler microbatch round-robin | débit +10–35 % ; P95 amélioré de 15–50 % | 0 % à vide | Moyen | Élevée | Conditionnelle au regroupement |
| M7 | Annulation à la frontière de batch | 10–100 % du reste sur abandon | 0 % nominal | Faible–moyen | Moyenne | Oui |
| M8 | Cache L1 worker | 60–95 % phase client sur hit | <1–3 % après M2 | Moyen | Moyenne–élevée | Oui sous profil exact |
| M9 | FlashAttention 2 | 5–25 % synthèse | 1–10 % | Moyen | Moyenne | Conditionnelle |
| M10 | Hash de référence calculé une fois par job | 80–95 % de ce sous-coût | <0,1–1 % | Très faible | Faible | Oui |
| M11 | Référence fixe déjà approuvée pour lever l’ancre initiale | 5–20 % synthèse selon la première scène | 0–8 % | Moyen si le timbre change | Faible | Oui seulement si référence identique au contrat |
| I1 | Scratch NVMe local + promotion durable | variable | 5–20 % si PVC lent ; 0–5 % sinon | Moyen | Moyenne–élevée | Oui |
| I2 | CPU Guaranteed/cpuset ou quotas explicites | 0–15 % à vide ; latence P95 −10–30 % sous contention | dépend du cluster | Faible | Moyenne | Oui |
| I3 | GPU MOSS dédié, requests/taints/affinity | évite 10–40 % de régression P95 | 0 % à vide | Faible | Moyenne | Oui |
| I4 | Pré-pull image + bundle/Chrome chauds | 30–90 % cold start | 0 % steady-state | Faible–moyen | Moyenne | Oui |
| I5 | Files et pods par classe de ressource | débit +10–40 %, P95 amélioré de 15–50 % sous charge | 0 % à vide | Moyen | Élevée | Oui sous limites |
| I6 | Stockage MOSS séparé : modèle/jobs/CAS | 10–50 % des phases froides/hit local si `/data` est lent | 0–5 % steady-state | Moyen | Moyenne | Oui |
| I7 | Probes, drain et grâce d’arrêt MOSS | 10–100 % du reste lors d’un drain | 0 % nominal | Moyen | Moyenne | Oui |
| I8 | Pods Remotion résidents, scale horizontal | débit flotte +50–200 % selon nœuds | 0 % mono-job | Moyen | Moyenne–élevée | Oui |

## 8. Optimisations explicitement déconseillées

- Baisser le final à 30 fps, 720p, 960×540 ou upscaler vers 1080p.
- Utiliser `scale=0.5` pour le livrable plutôt que seulement pour un smoke.
- Supprimer le smoke, le `tsc`, les validateurs, la revue finale, `freezedetect`, le QC audio, l’alignement, le mastering ou le loudnorm.
- Lancer plusieurs CLI smoke indépendantes au lieu de partager bundle et navigateur.
- Augmenter simultanément concurrence Remotion, Celery, stills et jobs sans budget CPU/RAM.
- Mettre les sources temporaires de plusieurs jobs dans le même `tsconfig` ou le même `publicDir`.
- Cacher par similarité sémantique du code, de la voix ou des rendus.
- Concaténer naïvement des MP4 H.264 rendus scène par scène.
- Utiliser le GPU MOSS pour Chromium/NVENC sans isolation et mesure de contention.
- Activer NVENC sur Remotion `4.0.400`, ou reprendre CRF 18 comme s’il s’appliquait à NVENC.
- Introduire une nouvelle référence de voix uniquement pour accélérer le premier segment.
- Multiplier les réplicas MOSS sur un unique GPU sans scheduler et capacité VRAM démontrés.
- Présenter le modèle chaud ou le CAS MOSS global comme un gain futur : ils existent déjà.

## 9. Prochaines étapes recommandées

### Phase 0 — Baseline et garde-fous

1. Figer un corpus 1920×1080 à 60 fps : catalogue, 3–4 Custom, 8 Custom, footage, formules/code, 60 s et 240 s.
2. Mesurer chaque phase avec des timestamps monotoniques et un `trace_id`.
3. Séparer bundle, lancement Chrome, frame rendering et encodage.
4. Enregistrer les valeurs effectives de concurrence, CPU, mémoire, stockage, batch MOSS, modèle/dtype/attention et référence.
5. Corriger ou neutraliser dans le protocole les anomalies de timings et de beats de revue.
6. Établir les seuils de non-régression avant tout benchmark.

### Phase 1 — Gains rapides sans changement de contenu

1. Isoler `tsc` et `publicDir`.
2. Télécharger les WAV dans `.part`, valider et renommer atomiquement.
3. Versionner la clé MOSS et épingler le profil de synthèse.
4. Benchmark Remotion avec concurrence entière.
5. Supprimer les MP3 internes inutiles et utiliser le WAV global.
6. Résoudre les hits CAS avant la FIFO GPU.
7. Mutualiser les extractions de revue/QC.

### Phase 2 — Chemin critique et réutilisation

1. Passer les smoke checks sur une entry multi-compositions avec bundle/Chrome uniques.
2. Ajouter un pool de deux stills et tester `scale=0.5`.
3. Benchmark MOSS `1/2/4`, puis bucketing.
4. Ajouter le cache exact TSX/attestation et la reprise par checkpoint.
5. Chevaucher scene-coder et MOSS uniquement pour les Custom.
6. Préparer l’audio masterisé pendant le rendu.
7. Déplacer le scratch sur NVMe local si les métriques confirment un goulot stockage.
8. Séparer le cache modèle, les jobs temporaires et le CAS MOSS selon leur durabilité.
9. Ajouter probes et drain coopératif avant les maintenances k3s.

### Phase 3 — Expériences conditionnelles

1. Dédupliquer/mémoriser les hotspots du catalogue avec snapshots de parité.
2. Tester Chromium GPU sur matériel séparé.
3. Mettre Remotion à niveau puis tester NVENC seulement si l’encodage est matériel.
4. Tester `@remotion/media` pour les jobs footage.
5. Introduire le scheduler MOSS inter-jobs et FlashAttention 2.
6. Étudier le cache de frames/plages seulement si les réparations restent une part importante.

## 10. Protocole de mesure

### 10.1 Corpus

- durées cibles : 60 s et 240 s ;
- 8–12 scènes ;
- catalogue pur, 3–4 Custom, 8 Custom ;
- un job avec footage ;
- code, formule, plot, sous-titres et transitions ;
- EN, FR et une langue non latine pour MOSS ;
- référence fixe approuvée et ancre implicite ;
- cache MOSS 0 %, 50 % et 100 % ;
- premier passage, repair d’une scène et doublon exact ;
- un job à vide, puis 2 et 4 jobs concurrents.

### 10.2 Métriques Remotion

- temps LLM Custom, `tsc`, bundle, ouverture Chrome et chaque still ;
- cache hits code/attestation/bundle ;
- `resolvedConcurrency`, `renderedDoneIn`, `encodedDoneIn` ;
- frames/s, slowest frames, CPU utile/throttlé, RSS/P95 et OOM ;
- IOPS, débit et espace scratch ;
- GPU SM/mémoire si Chromium GPU ; encodeur si NVENC ;
- nombre de backgrounds, coût KaTeX/Plot et scènes footage.

### 10.3 Métriques MOSS

- `synthesis_profile_id` et commit modèle ;
- queue wait, cache preflight, hits/misses ;
- batch configuré/effectif, longueurs et budget tokens ;
- temps GPU, decode, écriture WAV, cache et MP3 séparés ;
- secondes audio, RTF, VRAM et GPU util ;
- première URL disponible, job terminal, débit de téléchargement ;
- token caps, troncatures, OOM, annulations et erreurs ;
- temps padding, concat, mastering, loudnorm et AAC.

### 10.4 Métriques flotte

- P50, P95 et P99 ;
- débit jobs/heure ;
- âge maximal de file ;
- taux de succès first-pass et causes de réparation ;
- part catalogue/Custom/footage ;
- taux de hit par niveau de cache ;
- secondes réellement évitées, pas seulement nombre de hits ;
- cold start et steady-state séparés.

Chaque configuration doit être répétée au moins 5 à 10 fois. Une promotion exige un gain sur P50 **et** P95, sans hausse d’échecs, fallback, OOM ou variance qualité.

## 11. Garde-fous de non-régression

### 11.1 Visuel

- sortie 1920×1080 à 60 fps vérifiée par ffprobe ;
- même nombre de scènes, durées et transitions ;
- aucun upscaling depuis une résolution inférieure ;
- revue de plusieurs frames par scène ;
- OCR/lisibilité des petits textes, code et formules ;
- pixel-diff tolérant sur catalogue et transitions ;
- mêmes gates de freeze et même politique de finalisation.

### 11.2 Synchronisation

- durées calculées depuis les WAV validés ;
- cues et sous-titres dérivés de l’alignement réel ;
- aucune attente arbitraire pour masquer un écart ;
- durée audio/vidéo et frame de frontière comparées ;
- zéro désynchronisation introduite par le mastering parallèle.

### 11.3 Audio

- même modèle, commit, voix/référence, langue et paramètres pour une optimisation dite neutre ;
- WER et lexique STEM ;
- similarité du locuteur ;
- MOS/MUSHRA aveugle sur prosodie, pauses et naturel ;
- détection de troncature et token cap ;
- LUFS, true peak, clipping, silences et canaux ;
- mastering, loudnorm deux passes et AAC final conservés.

### 11.4 Seuils de départ à ratifier

- résolution/FPS : zéro violation ;
- taux de succès first-pass : baisse absolue ≤ 1 point ;
- fallback Custom : hausse ≤ 1 point ;
- WER : hausse absolue ≤ 0,5 point ;
- MOS : aucune baisse statistiquement significative > 0,2/5 ;
- aucun nouveau freeze, overflow, formule illisible ou défaut de transition ;
- aucune nouvelle corruption de cache ou réutilisation après changement de profil ;
- latence retenue seulement si P50 et P95 progressent.

## 12. Sources externes officielles

### Remotion

- [Performance Tips](https://www.remotion.dev/docs/performance)
- [Concurrency](https://www.remotion.dev/docs/terminology/concurrency)
- [`bundle()`](https://www.remotion.dev/docs/bundle)
- [`openBrowser()`](https://www.remotion.dev/docs/renderer/open-browser)
- [`renderStill()`](https://www.remotion.dev/docs/renderer/render-still)
- [`renderMedia()`](https://www.remotion.dev/docs/renderer/render-media)
- [Output scaling](https://www.remotion.dev/docs/scaling)
- [Using the GPU](https://www.remotion.dev/docs/gpu)
- [Hardware accelerated encoding](https://www.remotion.dev/docs/hardware-acceleration)
- [Version mismatch](https://www.remotion.dev/docs/version-mismatch)

### MOSS, audio et transport

- [MOSS-TTS v1.5 — model card](https://huggingface.co/OpenMOSS-Team/MOSS-TTS-v1.5)
- [Transformers — `from_pretrained`](https://huggingface.co/docs/transformers/main_classes/model)
- [FastAPI — `FileResponse`](https://fastapi.tiangolo.com/advanced/custom-response/#fileresponse)
- [FFmpeg — filters `apad`, `concat` et `loudnorm`](https://ffmpeg.org/ffmpeg-filters.html)

### Kubernetes, K3s et NVIDIA

- [Kubernetes — Resource Managers](https://kubernetes.io/docs/concepts/workloads/resource-managers/)
- [Kubernetes — Local ephemeral storage](https://kubernetes.io/docs/concepts/storage/ephemeral-storage/)
- [Kubernetes — Volumes et `emptyDir`](https://kubernetes.io/docs/concepts/storage/volumes/)
- [Kubernetes — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Kubernetes — Schedule GPUs](https://kubernetes.io/docs/tasks/manage-gpus/scheduling-gpus/)
- [K3s — NVIDIA Container Runtime](https://docs.k3s.io/advanced#nvidia-container-runtime)
- [K3s — Import Images](https://docs.k3s.io/add-ons/import-images)
- [NVIDIA — GPU Operator](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/overview.html)
- [NVIDIA — GPU sharing](https://docs.nvidia.com/datacenter/cloud-native/gpu-operator/latest/gpu-sharing.html)

## Conclusion

Le meilleur gain ne vient ni d’une baisse de qualité ni d’un remplacement de moteur ou de voix. Il vient de la suppression des coûts de coordination autour des composants déjà corrects : **quota CPU explicite, bundle/Chrome partagés, batch MOSS mesuré, cache servi avant la file, artefacts exacts réutilisés et PCM conservé jusqu’à l’AAC final**.

Dans un scénario favorable et illustratif où un job Custom cumule des misses MOSS et une concurrence Remotion mal réglée, ces leviers peuvent retirer **20–40 % du temps total après re-mesure**, sans additionner naïvement leurs maxima. Ce n’est pas une prévision du cluster en l’absence de télémétrie. Sur un job catalogue avec cache MOSS chaud, le gain attendu est plus modeste et se situe surtout dans le rendu, le fast-path cache et le post-traitement. Sur une réparation, les checkpoints et caches exacts peuvent éviter **50–90 % du travail de la tentative éligible**.

L’ordre de décision reste : **mesurer le chemin réel, isoler les ressources, retirer les encodages inutiles, régler les concurrences, réutiliser exactement, puis seulement expérimenter avec le GPU de rendu**.
