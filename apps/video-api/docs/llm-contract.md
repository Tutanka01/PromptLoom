# LLM Contract

L'API supporte n'importe quel endpoint compatible OpenAI, configure par :

```text
OPENAI_BASE_URL
OPENAI_API_KEY
OPENAI_MODEL
```

Le worker utilise le format Chat Completions.

## Objectif du LLM

Le LLM ne doit pas rendre la video directement.

Il doit produire un blueprint structure qui decrit :

- quoi enseigner ;
- quelles scenes creer ;
- quelle duree cible respecter ;
- quelle narration lire ;
- quelle composition visuelle suggerer par scene (`layout`, indicatif) ;
- quels beats visuels synchroniser avec la narration.

Le code Manim est ensuite ecrit, scene par scene, par une seconde etape d'authoring LLM
(`scene_coder`, guidee par `manim-skill.md`) qui produit du vrai Manim (LaTeX, axes, code,
diagrammes). Si une scene generee echoue (securite AST, syntaxe, compilation), le worker
retombe sur un template deterministe pour cette scene uniquement.

## Format attendu

Le LLM doit retourner un objet JSON :

```json
{
  "title": "What Is A Derivative?",
  "theme": "math",
  "slug": "what-is-a-derivative",
  "target_duration_seconds": 240,
  "subject_area": "math",
  "difficulty": "intro",
  "audience": "STEM learners meeting calculus for the first time.",
  "teaching_goal": "Explain a derivative as an instantaneous rate of change.",
  "learning_objectives": [
    "Connect average rate of change to instantaneous rate.",
    "Explain why the limit process creates a tangent slope."
  ],
  "style_notes": "Dark academic style, stable diagrams, clear arrows, one active concept at a time.",
  "scenes": [
    {
      "key": "Scene1_HookEN",
      "title": "The changing quantity",
      "duration_seconds": 30,
      "layout": "concept_map",
      "text": "A derivative begins with a simple question: how fast is something changing right now?...",
      "visual_intent": "Build a concept map from changing quantities to the question of instant rate.",
      "beats": [
        {
          "key": "question",
          "at": 0.08,
          "text_hint": "how fast is something changing",
          "visual_action": "Reveal the central question and connect it to example quantities."
        }
      ]
    }
  ]
}
```

## Validation

Le blueprint est valide par Pydantic.

Regles principales :

- `slug` en kebab-case minuscule.
- 3 a 14 scenes.
- par defaut, une video vise 240 secondes.
- `subject_area` vaut `math`, `physics`, `cs`, `biology`, `chemistry`, `engineering` ou `general_stem`.
- `difficulty` vaut `intro`, `intermediate` ou `advanced`.
- `learning_objectives` contient 1 a 5 objectifs concis.
- pour une cible 180-300 secondes, le blueprint doit utiliser 8 a 12 scenes.
- chaque scene a un `duration_seconds` coherent avec la duree cible.
- chaque scene choisit une primitive visuelle approuvee : `concept_map`, `process_flow`, `layered_system`, `timeline`, `equation_transform`, `graph_plot`, `comparison_table`, `cycle_diagram`, `spatial_model`, `recap_map`.
- chaque scene a une cle du type `Scene1_HookEN`.
- les numeros de scenes doivent etre ordonnes.
- chaque scene a 3 a 8 beats.
- les beats sont ordonnes par `at`.
- `at` est un ratio entre `0.0` et `1.0`.
- le dernier beat utile doit etre au moins vers `0.75`.

## Python Manim genere, mais sous garde-fous

Le LLM ecrit maintenant du vrai Manim par scene (pour la variete et le LaTeX), mais on
encadre le risque (code fragile ou dangereux : imports invalides, acces fichier/reseau,
scenes qui ne compilent pas) :

- LLM -> blueprint JSON structure ; Pydantic valide le JSON.
- `scene_coder` -> corps de `construct()` par scene, guide par `manim-skill.md`.
- `validate_scene_ast_security` : rejette imports interdits (`os`, `subprocess`, ...),
  `eval`/`exec`/`open`, et tout import hors liste blanche.
- `_validate_body_contract` : impose le contrat de synchro (`begin_sync` / `play_until` /
  `finish_sync`, pas de `self.wait`/`self.time`).
- `validate_scene_names` : rejette les noms indefinis (symbole Manim hallucine type
  `GlowDots`, helper inexistant) en les comparant a `dir(manim)` + helpers + locaux.
- `smoke_render_scene` : rend une frame de la scene isolee (`manim -ql -s`) pour prouver
  que `construct()` s'execute vraiment — attrape `NameError`, mauvais arguments, erreurs
  LaTeX, avant le render global. Desactivable via `VIDEO_API_SCENE_CODER_SMOKE_RENDER=0`.
  Ces deux checks ne tournent que la ou manim est installe (worker Docker).
- boucle de reparation par scene (`VIDEO_API_SCENE_CODER_ATTEMPTS`), puis fallback template
  deterministe si la scene ne passe toujours pas. C'est ce filet qui garantit qu'une scene
  fautive ne fait pas echouer tout le job (`failed_render`).
- `validate_static_video_source` + `py_compile` avant tout rendu.

Pour forcer l'ancien comportement 100% deterministe : `VIDEO_API_SCENE_CODER_ENABLED=0`.

## Reparation

Si le blueprint est invalide ou si une etape echoue, le worker peut appeler le LLM en mode reparation.

Il fournit :

- prompt original ;
- blueprint precedent ;
- type d'erreur ;
- message d'erreur.

Le nombre de tentatives est controle par :

```text
VIDEO_API_MAX_REPAIR_ATTEMPTS=2
```

## Conseils pour choisir un modele

Le modele doit etre bon en :

- JSON strict ;
- structuration pedagogique ;
- anglais narratif ;
- decomposition scene par scene ;
- description visuelle concrete.

Si le modele ne respecte pas bien le JSON, essayer :

```text
VIDEO_API_LLM_RESPONSE_FORMAT=json_object
```

seulement si l'endpoint le supporte.

## Mode fake

Pour tester sans LLM :

```text
VIDEO_API_FAKE_LLM=1
```

Le worker utilise alors un blueprint local deterministe.

## Contrat vision (revue visuelle)

Quand `VIDEO_API_VISION_ENABLED=1`, le worker appelle un second modele (vision) via le meme endpoint OpenAI-compatible.

### Entree

Un seul message utilisateur multimodal contenant :

1. Un bloc texte :
   - contexte JSON avec la liste des scenes : `scene_key`, `narration`, `visual_intent`, `active_beat`, `timestamp_seconds`.
   - instruction de notation (5 dimensions).
2. N blocs `image_url` (base64 PNG), un par scene, dans le meme ordre que la liste.

### Sortie attendue

Un objet JSON strict :

```json
{
  "scene_scores": [
    {
      "scene_key": "Scene1_HookEN",
      "dimensions": {
        "narration_match": 8,
        "readability": 9,
        "framing": 10,
        "density": 7,
        "not_blank": 10
      }
    }
  ],
  "issues": [
    {
      "scene_key": "Scene1_HookEN",
      "dimension": "readability",
      "severity": "blocker",
      "message": "Label clipped at right edge",
      "suggestion": "Shorten label to under 35 characters"
    }
  ],
  "summary": "Synthese courte en une phrase."
}
```

Chaque dimension est notee de 0 a 10. Les severites valides sont `blocker`, `major`, `minor`.

### Decision pass/fail (cote Python, pas LLM)

Le worker calcule :

```
score_scene = 10 * (narration_match*0.35 + readability*0.20 + framing*0.20 + density*0.15 + not_blank*0.10)
score_global = moyenne des scores de scene
passed = (score_global >= VIDEO_API_VISION_MIN_SCORE) ET (aucune issue severity=blocker)
```

Si `passed=False` : le `repair_hint()` (liste des issues blocker/major par scene) est injecte comme message d'erreur dans le prompt de reparation `repair_blueprint`.
