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

### Video a partir d'un document (PDF)

Pour expliquer un article scientifique, un cours ou un rapport, le PDF est
envoye une fois (`POST /v1/documents`) puis reference par `document_id` dans
`POST /v1/videos`. Voir api-reference.md pour les requetes, operations.md pour
la configuration.

- **Texte** : l'extraction decoupe le PDF par titres de section (bibliographie
  exclue). Chaque section devient une source citee `doc_NN`, budgetee pour tenir
  dans `VIDEO_API_DOCUMENT_PROMPT_CHARS`. Le blueprint explique ce document, pas
  le sujet en general ; la recherche web reste possible en plus
  (`research.enabled=true`), ses sources gardent les ids `src_NN`.
- **Figures** : chaque figure legendee (`Figure N`) est decoupee depuis la page
  en haute resolution (images et dessins vectoriels, labels compris), marges
  blanches rognees. Aucune ligne de texte courant (colonne voisine, paragraphe)
  n'est coupee dans la decoupe ; un fond blanc invisible qui chevauche la
  legende ne masque plus la figure. Le LLM en choisit 2 a 4 pour des
  `FigureScene`. Une amelioration de l'extraction incremente
  `EXTRACTOR_VERSION` (`documents.py`) : re-envoyer un PDF extrait par une
  version anterieure le re-extrait (et relance l'analyse vision).
- **FigureScene** : la figure est montree entiere sur une carte blanche, jamais
  recadree. Ses annotations numerotees apparaissent sur leurs cues de narration ;
  quand une annotation porte une zone (analyse vision, `VIDEO_API_VISION_MODEL`),
  la camera zoome sur cette zone et assombrit le reste, puis revient a la vue
  d'ensemble avec toutes les zones numerotees. Sans modele vision, les
  annotations sont listees a cote de la figure.
- **Garde-fous** : le LLM ne manipule que des ids (`fig_NN`, `rN`). Le worker
  copie le PNG depuis le stockage des documents, ignore les regions inconnues et
  remplace une figure inconnue par un diagramme. Les figures ne consomment pas
  le budget `visuals.max_assets` et ne dependent pas de `allow_stock`.
- **Limites** : pas d'OCR (PDF scanne refuse) ; une figure sans legende
  reconnaissable n'est pas extraite ; les tableaux ne sont pas decoupes (leur
  texte reste dans les sections). Reutiliser les figures d'un article dans une
  video publiee suppose d'en avoir le droit (licence du PDF).

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
  l'affichage garde les accents. Les scripts non latins (arabe, hebreu, persan,
  cyrillique) ne sont **pas** alignables par MMS_FA (charset a-z) : la video est
  rendue normalement mais sans sous-titres incrustes ni sidecar, et le rapport
  porte `alignment: failed`. Le texte a l'ecran reste, lui, dans la bonne
  direction (voir remotion-engine.md, *Direction du texte*) ;
- la meme liste de cues produit un sidecar `final/<slug>-<langue>.srt` + `.vtt`
  (timeline globale), liste dans `report.subtitles` et telechargeable via
  `/v1/videos/{id}/artifacts/<chemin>` — incruste et fichier ne peuvent pas
  diverger ;
- la bande-son est 100 % voix par choix editorial : aucune musique, aucun effet
  sonore, transitions de scene purement visuelles (fondus) ;
- **mastering voix + loudness** : `assemble_en.sh` masterise le voiceover
  (high-pass, de-esser, compression douce) puis le normalise (EBU R128,
  `loudnorm` deux passes) a une cible commune (`VIDEO_API_AUDIO_LOUDNESS_TARGET`,
  defaut -14 LUFS), donc le niveau percu ne depend plus du moteur TTS. Le QC
  mesure le final et signale clipping / quasi-silence
  (`reports/final/audio_stats.json`). Voir operations.md ;
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
