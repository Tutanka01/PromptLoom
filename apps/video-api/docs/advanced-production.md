# Production editoriale et cinematographique

Les modes avances sont actives **par requete API**. Ils ne modifient pas le
pipeline technique historique : un client qui n'envoie aucun nouveau champ
reste en `production_mode: "technical"`.

## Ce que les modes changent

| Mode | Moteur par defaut | Recherche | Captions | Promesse controlee |
|---|---|---|---|---|
| `technical` | configuration serveur | desactivee | `off` | explication technique |
| `editorial` | Remotion | activee | `full` | montage editorial anime |
| `cinematic` | Remotion 60 fps | activee | `full` | video conduite par le mouvement |

`cinematic` exige Remotion. `editorial` accepte un moteur explicite, mais
Remotion est recommande pour les captions alignees, les medias et les
transitions.

Exemple :

```bash
curl -X POST http://localhost:8080/v1/videos \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Explique pourquoi un appel systeme traverse une frontiere de privilege",
    "theme": "linux-fondamentaux",
    "language": "fr",
    "target_duration_seconds": 240,
    "quality_profile": "high",
    "production_mode": "cinematic",
    "research": {"enabled": true, "required": true, "max_sources": 10},
    "visuals": {"strategy": "hybrid", "allow_stock": true, "max_assets": 4},
    "captions": "full"
  }'
```

## Pipeline avance

```text
recherche sourcee
  -> proposition editoriale
  -> blueprint + source_ids
  -> scene plan + motion preflight
  -> acquisition locale des medias
  -> TTS + alignement mot a mot
  -> sous-titres (cues globaux + sidecar .srt/.vtt) si captions != off
  -> Remotion (motion design + piste de sous-titres continue)
  -> voix + musique duckee optionnelle
  -> ffprobe + freezedetect + delivery gate
```

### Recherche

Le worker appelle Tavily ou Exa **avant** le LLM. Il stocke un dossier borne
dans `research.json` et fournit au modele des extraits avec des identifiants
stables (`src_01`, `src_02`, ...). Les `source_ids` inconnus produits par un
modele sont supprimes. Dans un batch multilingue, les videos secondaires
reutilisent le dossier de la primaire.

Configuration serveur :

```text
VIDEO_API_RESEARCH_PROVIDER=tavily   # tavily | exa
VIDEO_API_RESEARCH_API_KEY=...
VIDEO_API_RESEARCH_TIMEOUT_SECONDS=45
```

La recherche est requise par defaut en `editorial` et `cinematic`. Sans
provider configure, le job echoue explicitement en `failed_generation`. Pour
un environnement hors ligne, envoyer `research.required: false` ou desactiver
la recherche ; le rapport indique alors l'absence de sources.

### Medias et provenance

Une scene ne fournit jamais une URL arbitraire. Elle demande un media par
`asset_query`. Le worker interroge un provider autorise, telecharge le fichier
avant le rendu, controle domaine, type MIME et taille, calcule son SHA-256 puis
ecrit `asset_manifest.json`. Le renderer ne fait aucun acces reseau.

Le premier adapter est Pexels :

```text
VIDEO_API_ASSET_PROVIDER=pexels
VIDEO_API_PEXELS_API_KEY=...
VIDEO_API_ASSET_MAX_DOWNLOAD_MB=80
```

Si un media manque, depasse le budget ou echoue a la validation, la scene
retombe sur un diagramme `BulletScene` deterministe. Il n'y a ni frame vide ni
URL distante cachee. Pour les sujets kernel, `visuals.strategy: "hybrid"`
garde les diagrammes comme langage principal et reserve le B-roll aux moments
ou il apporte une information exacte.

### Motion design, captions et son

- `ImageScene` anime les photos par Ken Burns, panoramique ou push-in.
- `FootageScene` boucle proprement un clip local avec un traitement editorial.
- les transitions sont des overlays aux frontieres de scenes : elles ne
  chevauchent pas la timeline et ne desynchronisent donc jamais la voix ;
- les sous-titres sont une **piste unique continue** posee au-dessus de toute la
  timeline (pas par scene, pas conditionnee aux beats), donc homogene et stable
  pendant les transitions. `full` (et `keywords`, conserve par compatibilite) la
  rendent en continu ; `off` la masque ;
- `pipeline/captions.py` regroupe les mots alignes (`audio/en/alignment.json` ->
  `captions`) en cues lisibles (1-2 lignes equilibrees, coupees sur la
  ponctuation) affichant le vrai texte (casse, ponctuation, accents, chiffres
  reels), pas la forme normalisee de l'aligneur, et ecrit la liste globale dans
  `subtitles.json` (consommee par Remotion). Le multilingue latin (francais
  inclus) est gere : les diacritiques sont replies cote alignement seulement,
  l'affichage garde les accents. Sans alignement, les scenes restent rendables
  (sans sous-titres) ;
- la meme liste de cues produit un sidecar `final/<slug>-<langue>.srt` + `.vtt`
  (timeline globale), liste dans `report.subtitles` et telechargeable via
  `/v1/videos/{id}/artifacts/<chemin>` — incruste et fichier ne peuvent pas
  diverger ;
- les transitions de scene sont purement visuelles (fondus, aucun effet sonore
  ajoute aux coupes). Une musique configuree avec `VIDEO_API_MUSIC_FILE` reste
  duckee sous la narration ;
- **loudness** : `assemble_en.sh` normalise le rendu (EBU R128, `loudnorm`) a une
  cible commune (`VIDEO_API_AUDIO_LOUDNESS_TARGET`, defaut -14 LUFS), donc le
  niveau percu ne depend plus du moteur TTS. Le QC mesure le final et signale
  clipping / quasi-silence (`reports/final/audio_stats.json`). Voir operations.md ;
- **direction artistique** : le blueprint choisit une palette `art_direction`
  (default/blueprint/forest/synthwave/carbon/plum) adaptee au sujet ; `default`
  garde le look historique. Detail dans remotion-engine.md.

### Gate anti-diaporama

Avant le rendu, `motion_plan_report.json` mesure :

- couverture de mouvement ;
- repetition des composants ;
- proportion de scenes dominees par le texte ;
- couverture des beats et des sources ;
- diversite des medias et composants.

Un mode avance qui ne tient pas son seuil est repare par le LLM puis rejete si
les tentatives sont epuisees. Apres le rendu, le delivery gate combine ce plan
avec le ratio de frames gelees et le plus long segment statique. Une video peut
donc etre techniquement lisible par ffprobe et tout de meme etre refusee parce
qu'elle ne tient pas sa promesse editoriale.

Le rapport distingue `blocking_issues` et `warnings`. Un plan cinematique sans
media n'est pas automatiquement un echec lorsqu'il est varie, entierement cale
sur les beats et conduit par des composants animes : il passe le preflight avec
un avertissement, puis doit encore satisfaire le gate mesure sur le rendu reel.
Un plan textuel, repetitif ou insuffisamment synchronise reste bloque. Les
reparations recoivent le rapport complet et doivent modifier reellement le mix
de composants ; elles ne peuvent plus repondre par le meme plan en boucle.

## Artefacts inspectables

Ils sont accessibles avec
`GET /v1/videos/{job_id}/artifacts/{chemin}` :

```text
research.json
proposal.json
scene_plan.json
asset_manifest.json
motion_plan_report.json
blueprint.json
reports/report.json
```

`reports/report.json` inclut la configuration de production resolue, le nombre
de sources, le plan de mouvement et le resultat final `delivery`.
