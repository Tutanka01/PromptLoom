# Banque de voix MOSS

Ce dossier est monté en lecture seule dans les conteneurs `api` et `worker`
(`/data/voices`, configurable via `VIDEO_API_VOICE_BANK_DIR`). Chaque WAV
déposé ici devient une voix sélectionnable par requête quand le moteur vocal
est `moss` ou `moss-remote` (MOSS-TTS clone le timbre du WAV de référence).

## Format

- `<voice-id>.wav` — obligatoire. 5 à 20 secondes de parole propre suffisent.
  `voice-id` = lettres/chiffres/`-`/`_` (max 64 caractères), c'est la valeur à
  passer dans le champ `voice` de `POST /v1/videos`.
- `<voice-id>.json` — optionnel, métadonnées affichées par `GET /v1/voices` :

```json
{
  "label": "Sarah — femme (FR)",
  "description": "Voix féminine posée, adaptée aux explications techniques.",
  "languages": ["fr", "en"],
  "reference_text": "Transcription exacte du WAV de référence."
}
```

`languages` omis = la voix est proposée pour toutes les langues (le clonage
MOSS est multilingue). `reference_text` est transmis au moteur local si le
modèle en a besoin.

## Notes

- Sans voix sélectionnée, MOSS reste en timbre « libre » : le premier segment
  échantillonne une voix non déterministe, clonée ensuite sur le reste de la
  vidéo. Déposer une référence ici est le seul moyen de fixer le timbre.
- Le cache audio par segment est fingerprinté sur le chemin de la référence :
  remplacer le *contenu* d'un WAV en gardant le même nom ne réinvalide pas les
  segments déjà synthétisés — renommez le fichier (nouvel id) dans ce cas.
- Ne rien mettre d'autre que des paires WAV/JSON ici ; pas de données de jobs.
