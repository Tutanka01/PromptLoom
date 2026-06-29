# PromptLoom Studio — front-end de pilotage de l'API vidéo

Date : 2026-06-29 · App : `apps/studio/`

## But

Un front-end interne ("insider") soigné qui consomme **toutes** les options de
l'API `video-api` : créer des vidéos, suivre la progression en direct, regarder
le rendu final, inspecter rapport et artefacts. Qualité UI/UX élevée, **mode
clair uniquement**.

## Décisions (validées en brainstorming)

- **Stack** : React + TypeScript + Vite + TailwindCSS (v4). Cohérent avec le
  React déjà présent (Remotion).
- **État serveur** : TanStack Query (cache + polling des statuts, stoppe sur état
  terminal). Pas de Redux.
- **Formulaire** : react-hook-form + zod, schéma zod aligné sur le contrat
  Pydantic (bornes identiques).
- **Routing** : React Router (`/`, `/create`, `/videos/:id`, `/batches/:id`).
- **Service & CORS** : conteneur nginx qui sert le build statique **et**
  reverse-proxy `/v1/*` + `/healthz` → service `api:8080`. Même origine → aucun
  CORS à ajouter à FastAPI. Ajouté à la stack compose (port hôte 3000).
- **Auth** : panneau Réglages → clé `X-API-Key` collée, stockée en `localStorage`,
  envoyée par le client fetch. Lecture vidéo via `fetch` blob (le header passe)
  puis `URL.createObjectURL`.
- **Dev** : `npm run dev` + proxy Vite vers `localhost:8080`.

## Périmètre

Cœur (toujours) : création (toutes options), dashboard + liste avec statut live,
détail + progression live + lecteur, annulation.
Insider en plus : **vue batch multilingue**, **rapport de vérification**,
**explorateur d'artefacts**. Pas d'indicateur santé dédié.

Hors périmètre (anti usine à gaz) : pas d'auth multi-utilisateur, pas de SSR, pas
d'édition de blueprint, pas de websockets (l'API ne fait que du polling).

## Surface API consommée

| Endpoint | Usage UI |
| --- | --- |
| `POST /v1/videos` | Formulaire de création (mono + batch `languages[]`) |
| `GET /v1/videos` | Dashboard (filtre statut, pagination) |
| `GET /v1/videos/{id}` | Détail + polling progression |
| `DELETE /v1/videos/{id}` | Annulation |
| `GET …/download` | Lecteur (fetch blob) + bouton MP4 |
| `GET …/report` | Onglet Rapport |
| `GET …/artifacts/{path}` | Explorateur d'artefacts, sous-titres |
| `GET /v1/batches/{id}` | Vue batch |
| `GET /healthz` | Point santé discret dans la barre |

## Direction visuelle — « console de production »

Mode clair, sobre, précis. Évite explicitement les défauts génératifs
(cream-serif, dark-acid, broadsheet).

- **Palette** : fond cool near-white `#F6F8FB`, surfaces `#FFFFFF`, bordures
  hairline `#E4E9F0`, encre `#0C1322`, muted `#5A6678`. Accent indigo `#4F46E5`
  (brand). Sémantique : success `#16A34A`, danger `#DC2626`, queued neutre.
- **Typo** : Space Grotesk (display/wordmark/grands nombres), Inter (UI),
  JetBrains Mono (ids, timecodes, noms d'étapes, logs).
- **Signature** : la **Stage Rail**. La progression d'un job est rendue comme le
  transport d'un banc de montage : étapes du pipeline (queued → blueprint →
  narration → render → checks → done) ; l'étape active pulse pendant le rendu ;
  les segments se remplissent à l'avancement. Compacte sur les cartes du
  dashboard, complète et labellisée (mono) sur la page détail. Elle encode le
  vrai `current_step`, pas de la décoration.

Plancher qualité : responsive jusqu'au mobile, focus clavier visible, motion
réduite respectée (`prefers-reduced-motion`).

## Arborescence

```
apps/studio/
  Dockerfile            # build node → servi par nginx
  nginx.conf            # static + proxy /v1, /healthz → api:8080
  compose.yaml          # service studio (inclus depuis le compose racine)
  package.json, vite.config.ts, tsconfig*.json
  index.html
  src/
    main.tsx, App.tsx, router.tsx
    api/{client.ts, types.ts, queries.ts}   # fetch + X-API-Key, TanStack Query
    lib/{settings.ts, format.ts, steps.ts}
    components/                              # primitives + Stage Rail, StatusPill…
    features/{dashboard, create, job, batch, settings}/
    index.css                               # tokens Tailwind v4 (@theme)
```

Le compose racine inclut `apps/studio/compose.yaml` à côté de video-api ; le
service `studio` dépend de `api` et expose `3000:80`.
