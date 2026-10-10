# Validation du corpus scientifique local — 10–11 octobre 2026

## Périmètre

Le [catalogue](../knowledge/README.md) décrit 13 fiches externes et leurs sources
primaires. Le [manifeste](../knowledge/corpus.json) sélectionne ces fiches et
trois documents internes. L'index local contient 24 passages. Aucun appel aux
URL des sources, aucune API NASA et aucune inférence cloud pendant les essais.

La recherche porte sur navigation, caméra/pose/repères, communications,
éclairage lunaire, détection, confiance et suivi. Les abstracts et notices des
quatre articles sont résumés ; ce travail ne prétend pas reproduire leurs
expériences. Les textes distinguent explicitement les connaissances des sources
et les capacités effectivement intégrées à C.R.A.T.E.R.

## Recherche avec le véritable embedding

[Résultats détaillés](assistant-corpus-retrieval.json) : 13/13 passages attendus
en première position (donc 13/13 dans les quatre premiers). EmbeddingGemma 300M
déjà installé, Ollama local CPU ; 19,145 secondes cumulées pour les 13 recherches.
Les questions sont préparées et proches du corpus : ce résultat est un contrôle
de récupération, pas une mesure de précision sur des questions inédites.

Reproduire depuis la racine du dépôt, avec les modèles locaux déjà installés :

```powershell
$corpus = Get-Content docs/knowledge/corpus.json -Raw | ConvertFrom-Json
$sources = $corpus.files
python -m crater_assistant index @sources --output artifacts/assistant-research-index.json
python scripts/evaluate_assistant_corpus.py --index artifacts/assistant-research-index.json --output artifacts/new-corpus-retrieval.json
```

Le script refuse d'écraser un rapport existant et vérifie la sélection exacte
des sources ainsi que les empreintes de l'index. Les empreintes publiées
correspondent aux octets de ce PC ; des fins de ligne différentes imposent
une reconstruction locale et peuvent changer ces empreintes.

## Vérifications automatisées

262 tests Python réussis, trois tests optionnels ignorés faute de poids/runtime
ONNX appropriés. Sept tests du client M3 réussis et compilation TypeScript
stricte réussie. Les tests contrôlent entre autres conservation des références,
refus des domaines usurpés, manifestes cohérents et limites conservées dans le
même passage. Ces tests n'évaluent pas la vérité de chaque réponse du LLM.

Le commit de corpus `70ac3ca` a passé la
[CI Python 3.11/3.12 et intégration M3](https://github.com/omarfh111/C.R.A.T.E.R/actions/runs/38093167757).
La validation GPU réelle M1 sur le PC RTX 5070 reste un essai distinct ; aucun
résultat ONNX réel n'est remplacé par ces tests documentaires.

## Réponses du véritable LLM via le client M3

[Trace HTTP complète](assistant-research-http.json), Qwen3 4B Instruct quantifié
Q4_K_M et EmbeddingGemma 300M dans Ollama local CPU. Les questions sont envoyées
avec `topK=4` via `createAssistantClient`, au sidecar temporaire sur le port 8768.
Les sources reçues conservent URL, date et citations, y compris ESA et arXiv.
Les chemins sont réduits aux noms de fichiers pour ne pas publier le chemin
personnel du PC.

| Question | Statut attendu et obtenu | Temps CPU |
|---|---|---|
| Cadence NASA | Réponse sourcée | 89,356 s |
| Essais ESA Lucid | Réponse sourcée | 78,929 s |
| Confiance de 0,9 | Réponse sourcée | 96,910 s |
| Température actuelle inconnue | Sources insuffisantes | 62,703 s |

Ces temps sont ceux de ce PC, incluant recherche et génération ; aucune
promesse de vitesse sur le PC M1/M3 n'en est déduite.

La relecture porte sur les conclusions attendues : distance de capture NASA
distincte du FPS de lecture ; essais ESA terrestres et non validation laser ;
score de 0,9 sans garantie de 90 % de réussite ; abstention sur une température
courante du rover inconnue. La réponse sur la confiance ajoute une digression
sur profondeur/pose, inutile à cette question : ce contrôle ne certifie pas
chaque explication causale ou la pertinence de chaque phrase.

Un premier essai ESA avait inventé un lien entre Lucid et l'alimentation laser
et nié le rôle des analogues terrestres. La fiche et le prompt ont été clarifiés,
l'index reconstruit et les essais rejoués. La trace publiée correspond au dernier
essai ; le problème initial montre pourquoi des citations valides seules ne
prouvent pas la vérité. Pour les décisions spatiales et les métriques, conserver
les validations déterministes M2 et les observations calibrées.

Pour rejouer une réponse : démarrer `serve` avec l'index du manifeste, puis
envoyer une question de la trace via le client M3 ou utiliser `ask --index`.
Les essais ne téléchargent aucune page NASA/ESA/arXiv. Les contrôles CI utilisent
des doubles de modèle explicites ; ils ne sont pas présentés comme inférence
réelle. Éviter les générations CPU en parallèle de fenêtres courtes de capture
M1 sans mesurer l'impact sur le PC cible.
