# Assistant local : composant prêt pour M3

Le [journal d'expérience et diagnostic asynchrone](experience-integration.md)
ajoute des endpoints facultatifs quand `serve --journal` est utilisé. Il prépare
les références d'images ; l'analyse des pixels reste différée.

Ce composant explique les documents sélectionnés et un rapport M2 choisi par
l'opérateur. Il est indépendant du WebSocket de télémétrie v1 : aucune trame
M1/M2/M3 n'est modifiée. Le panneau React reste à intégrer par M3 ; le client
TypeScript fourni dans `integrations/m3-assistant-client.ts` ne dépend pas de React.

## Démarrage hors ligne

Les deux modèles doivent déjà être installés dans Ollama : `embeddinggemma:300m`
et `qwen3:4b-instruct-2507-q4_K_M`. Aucun téléchargement automatique ni modèle
cloud n'est accepté. La consultation des sources a lieu pendant la préparation ;
les questions utilisent exclusivement les résumés locaux relus.

Depuis le checkout M2, reconstruire l'index puis démarrer le sidecar :

```powershell
$corpus = Get-Content docs/knowledge/corpus.json -Raw | ConvertFrom-Json
$sources = $corpus.files
python -m crater_assistant index @sources --output artifacts/assistant-nasa-index.json
python -m crater_assistant serve --index artifacts/assistant-nasa-index.json --port 8766
```

Pour ajouter un rapport terminé et valide, ajouter `--report artifacts/m2-report.json`
à `serve`. Le serveur choisit ce fichier ; le navigateur ne peut pas choisir un
chemin arbitraire. Les taux et compteurs du rapport sont calculés par Python,
puis expliqués par le LLM. Ce rapport n'est pas un flux de télémétrie live et
ne doit pas être présenté comme la position courante du rover.

Le PDF ATEC privé peut être ajouté après extraction avec `import-pdf` et
reconstruction explicite de l'index. Son texte n'est pas publié dans Git.

## Contrat HTTP

Base : `http://127.0.0.1:8766`. Origines de dashboard autorisées : HTTP
`localhost`, `127.0.0.1` ou `[::1]`, ports 5173 et 4173. L'Host doit correspondre
au serveur local. En pratique le serveur écoute sur 127.0.0.1.

| Appel | Résultat |
| --- | --- |
| `GET /health` | `status: ready`, `indexedChunks`, `llm`, `embedding` |
| `POST /ask` | JSON `{ "question": "...", "topK": 4 }`, topK optionnel |
| `OPTIONS /ask` | Préflight CORS pour le navigateur |

Question : 1 à 2000 caractères, `topK` de 1 à 8, corps JSON de 16 Ko maximum.
La réponse contient `status`, `answer`, `sources`, `citedSourceIds`, `facts`,
`models`, `roles`, `limitations` ; les types exacts figurent dans le client fourni.
Chaque source a un identifiant `[S1]`, un texte, un chemin local, une empreinte
et des lignes. Les résumés sourcés ajoutent `sourceUrl` et `verifiedOn`.

`answered` signifie que le format et les citations passent les contrôles.
`insufficient_evidence` est une réponse valide indiquant un manque de preuves.
Les citations connues ne garantissent pas la vérité de toutes les phrases.
`/health` vérifie le service HTTP, pas la disponibilité réelle des poids Ollama.

| HTTP | Traitement attendu dans le panneau |
| --- | --- |
| 200 | Afficher la réponse ou le manque de preuves, avec les passages |
| 400 | Corriger la question ou les paramètres |
| 403 | Vérifier Host/Origin ; ne pas élargir CORS à tous les sites |
| 503 | Modèles, index ou rapport indisponibles ; proposer un nouvel essai |

Afficher le texte comme texte, jamais comme HTML brut. Les liens externes sont
facultatifs et validés comme HTTPS NASA/ESA/arxiv.org ; les chemins locaux sont des libellés,
pas des URL web. Montrer les limites des preuves et le caractère simulé des
rapports concernés. L'assistant ne commande jamais le rover.

## Utilisation dans M3

Copier le client dans le dossier `src` du checkout M3, ou l'importer depuis
`integrations` dans un checkout intégré. Exemple pour le handler du formulaire :

```typescript
import { createAssistantClient } from './m3-assistant-client';

const assistant = createAssistantClient();
const result = await assistant.ask('Comment fonctionne AutoNav ?', 4);
// result.status, result.answer et result.sources alimentent le panneau M3.
```

Une question à la fois : le sidecar sérialise les appels. Désactiver le bouton
pendant l'attente, afficher l'état de chargement et gérer le timeout réseau.
Le client attend au maximum 240 secondes par défaut ; le backend Ollama a un
timeout de 180 secondes par appel. L'assistant en CPU peut prendre une minute
ou plus. Ne pas appeler le LLM à chaque trame de télémétrie ni sonder `/health`
pendant une génération. `--gpu` est une option globale du CLI si l'opérateur
dispose d'un budget GPU suffisant ; le CPU reste le défaut pour préserver M1.
Ce choix préserve la VRAM, mais ne supprime pas la concurrence CPU. Un essai
local a dépassé la fenêtre de trois secondes d'un test de perception pendant
une génération. Valider la coexistence sur le PC de démonstration ; éviter les
générations pendant une courte fenêtre de capture ou le démarrage de M1.

## Vérification reproductible

Les tests du client n'utilisent aucun LLM ni téléchargement :

```powershell
node --test integrations/m3-assistant-client.test.mjs
python -m pytest tests/test_assistant.py tests/test_assistant_sources.py tests/test_assistant_m3_client.py -q
```

Node >=22.18 est nécessaire pour importer le client TypeScript dans ces tests.
Le test Python ignore cette intégration si Node n'est pas disponible ; en CI,
elle est relancée explicitement avec Node 24 et vérification stricte des types.

Pour le véritable test Ollama, garder le sidecar démarré dans un terminal et
exécuter dans un autre, avec un nouveau nom de fichier de sortie :

```powershell
node integrations/smoke-assistant.mjs http://127.0.0.1:8766 artifacts/assistant-http-smoke-01.json
```

Le smoke passe par le même client que M3, vérifie une citation de la notice NASA
et l'abstention sur une température de rover inconnue. Il exporte les réponses
et les temps. Relire les explications causales manuellement ; deux exemples ne
constituent pas une évaluation générale de précision. La validation commune du
dashboard et de la perception ONNX reste à réaliser sur le PC M1/M3.

Les [résultats du smoke réel](validation/assistant-nasa-http.json) conservent
les deux réponses relues et leurs sources : environ 76 et 83 secondes en CPU
sur cette machine. Les essais initiaux ont montré des confusions causales ;
les passages et consignes ont été clarifiés avant cette validation finale.
Ces durées et ces deux réponses ne prédisent pas les performances d'autres runs.
