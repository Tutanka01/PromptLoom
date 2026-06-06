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
- quelle narration lire ;
- quels beats visuels synchroniser avec la narration.

Le code Manim est ensuite genere par le worker a partir de templates.

## Format attendu

Le LLM doit retourner un objet JSON :

```json
{
  "title": "What Is A Linux Syscall?",
  "theme": "linux-fondamentaux",
  "slug": "what-is-a-linux-syscall",
  "audience": "Developers learning Linux internals.",
  "teaching_goal": "Explain why user programs use syscalls to ask the kernel for privileged work.",
  "style_notes": "Dark technical style, stable cards, clear arrows, one active concept at a time.",
  "scenes": [
    {
      "key": "Scene1_HookEN",
      "title": "A command is not direct",
      "text": "A command looks simple, but the program does not talk directly to hardware...",
      "visual_intent": "Show terminal, program, blocked direct hardware path, then kernel path.",
      "beats": [
        {
          "key": "command",
          "at": 0.08,
          "text_hint": "A command looks simple",
          "visual_action": "Reveal the terminal command."
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
