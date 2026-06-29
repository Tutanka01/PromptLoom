# PromptLoom Studio

Front-end de pilotage de l'API `video-api`. SPA React + TypeScript + Vite +
Tailwind, mode clair, esthétique « console de production ». Il consomme toute la
surface publique de l'API : créer des vidéos (toutes les options), suivre la
progression en direct, regarder le rendu final, inspecter rapport et artefacts,
suivre les batches multilingues.

## Développement

```bash
cd apps/studio
npm install
npm run dev        # http://localhost:3000, proxy /v1 + /healthz -> localhost:8080
```

Pour viser une autre API en dev :

```bash
VITE_API_TARGET=http://mon-hote:8080 npm run dev
```

Lance l'API en parallèle depuis la racine (`docker compose up api worker`).

## Build

```bash
npm run build      # tsc -b && vite build -> dist/
npm run preview    # sert le build localement
```

## Stack intégrée (Docker)

Le service `studio` est inclus dans le `compose.yaml` racine. nginx sert le build
et reverse-proxy `/v1` + `/healthz` vers le service `api` (même origine : pas de
CORS, la lecture vidéo fonctionne, et l'en-tête `X-API-Key` est transmis tel quel).

```bash
docker compose up studio        # http://localhost:3000 (STUDIO_PORT pour changer)
```

## Authentification

Si l'API exige une clé (`VIDEO_API_KEYS` défini côté serveur), saisis-la dans
**Réglages** (en haut à droite). Elle est stockée en `localStorage` et envoyée en
en-tête `X-API-Key`. Les téléchargements (MP4, sous-titres, snapshots) passent par
un `fetch` authentifié + blob, car une balise native ne peut pas porter ce header.

## Architecture

```
src/
  api/         client fetch (X-API-Key), types miroir des schémas, hooks TanStack Query
  lib/         settings (localStorage), formatage, modèle d'étapes (steps), statut
  components/  primitives UI, StageRail (signature), StatusPill, Drawer, Toast, JsonView
  features/    dashboard · create · job · batch · settings
```

- **Progression** : polling TanStack Query, qui s'arrête de lui-même quand un job
  atteint un état terminal.
- **Stage Rail** : `lib/steps.ts` mappe le `status` du worker (qui parcourt le
  pipeline) sur un transport d'étapes lisible. C'est la source de vérité de
  l'élément signature ; garde-la fidèle au pipeline réel.
- **Formulaire** : `react-hook-form` + `zod`, schéma aligné sur le contrat
  Pydantic ; les règles inter-champs reflètent `ProductionOptions.resolve_defaults`.
