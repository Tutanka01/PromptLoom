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
- quelle primitive visuelle utiliser par scene ;
- quels beats visuels synchroniser avec la narration.

Le code Manim est ensuite genere par le worker a partir de templates.

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

## Pourquoi ne pas demander du Python brut au LLM

Le LLM peut produire du code fragile ou dangereux :

- imports invalides ;
- chemins absolus ;
- scenes qui ne compilent pas ;
- visuels sans lien avec la narration ;
- commandes arbitraires.

La v1 limite ce risque :

- LLM -> JSON structure.
- Pydantic valide le JSON.
- Worker -> Python Manim depuis templates.
- Validation statique avant execution.

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
