# Journal d'expérience prêt pour M3

Ce composant ajoute une mémoire des événements et un diagnostic local en
arrière-plan. Le WebSocket canonique v1 reste le canal de télémétrie ; le journal
est un sidecar indépendant. M1/M3 doivent encore brancher leur producteur
d'incidents sur cette API. Aucun détecteur universel d'incident ni pilote moteur
n'est ajouté. Une fois un incident transmis avec `analyze: true`, le composant
choisit une question selon son type et lance l'analyse automatiquement.

## Démarrage

Avec l'index du [corpus relu](knowledge/README.md) et les deux modèles Ollama
déjà installés :

```powershell
python -m crater_assistant serve --index artifacts/assistant-research-index.json --journal artifacts/experience.sqlite --media-root outputs/m1-live --port 8766
```

`--media-root` est facultatif sans images. Il désigne un dossier choisi par
l'opérateur, pas un chemin fourni par le navigateur. Sans `--journal`, les
endpoints existants conservent leur fonctionnement. Le statut `/health`
indique `experience.workerAlive`, `capacity` et `imageInference: false` ;
`ready` ne garantit pas que les poids Ollama sont disponibles.

SQLite fournit des transactions et un journal WAL. Un verrou système autorise
un seul worker par base, même entre processus. Un appel modèle est exécuté à
la fois. Pendant une analyse, ingestion, liste, polling et health restent
disponibles ; un `/ask` concurrent reçoit 429 et ne crée pas une file cachée.

## Événement v1 du composant

Champs requis : UUID canonique `eventId`, `roverId` (<=100 caractères),
`capturedAt` ISO avec fuseau (<=64 caractères), `kind`, `provenance`, `summary`
(<=2000 caractères). La provenance est déclarée par le producteur, pas certifiée.

Types : `telemetry_stale`, `link_changed`, `tracking_warning`,
`calibration_missing`, `operator_note`. Une observation tardive ne prouve pas
à elle seule une coupure radio. Le producteur choisit le type d'après ce qu'il
a effectivement observé, et transmet les éléments disponibles.

Provenances : `measured`, `simulated`, `operator`. Options :

- `question` : question spécifique <=2000 caractères ; sinon question par type.
- `decision` : `{ action, reason }`, textes <=1000 caractères chacun, motif
  effectivement enregistré par la politique/opérateur. Ce n'est pas un
  raisonnement interne reconstruit par le LLM.
- `frame` : trame complète v1 validée par M2 ; rover et instant de capture
  doivent correspondre à l'événement. Réutiliser `frame.capturedAt`, pas l'heure
  d'arrivée ; le serveur ajoute séparément `recordedAt`.
- `images` : <=4 références `{ relativePath, mediaType, sha256 }`, PNG/JPEG
  <=5 MiB et 20 millions de pixels chacune. Chemins relatifs avec `/`, dans
  la racine configurée, fichiers existants et empreintes vérifiées. Une
  référence ne prouve pas l'association à une capture : le producteur doit
  fournir la bonne image. Aucune récupération de média à partir d'une URL.

L'événement entier est limité à 32 KiB. Un UUID rejoué avec le même contenu
est idempotent ; un contenu différent est refusé. L'analyse cite un extrait
de cet événement sous `experience:<UUID>`, avec empreinte. Pour borner le
contexte : résumé <=500 caractères, action/motif <=250 chacun, au plus huit
dangers (moins si leur taille l'exige), nombre total de dangers conservé.
L'événement original reste consultable intégralement dans le journal.

## API et client M3

| Requête | Résultat |
|---|---|
| `POST /experience/events` avec `{event, analyze?: boolean}` | 201 : `{event, analysis}` ; enregistrement durable avant analyse |
| `GET /experience/events` | 50 derniers événements |
| `GET /experience/events/<UUID>` | Événement complet |
| `POST /experience/analyses` avec `{eventId, retry?: boolean}` | Travail queued/running/completed/failed ; doublon idempotent |
| `GET /experience/analyses/<UUID>` | État, question, tentative, résultat et erreur éventuelle |

Le résultat d'analyse conserve le contrat `AssistantAnswer` : passages,
citations, statut answered/insufficient_evidence. `completed` signifie que
le traitement est terminé, pas que le diagnostic est scientifiquement validé.
L'événement et la sortie du LLM sont stockés séparément.

File maximale : 16 travaux queued/running. Une saturation renvoie **429** ;
si un événement venait d'être soumis, il reste enregistré. Après libération,
demander son analyse par le même eventId. Une panne du modèle donne failed,
avec erreur générique ; `retry: true` est explicite, au plus cinq tentatives.
Les tentatives terminées restent dans l'historique. Après interruption du
processus, queued reprend ; running devient failed et exige un retry. Après
une erreur SQLite qui arrête le worker, vérifier health et relancer le service.

HTTP loopback, Host et origines M3 contrôlés comme dans le
[contrat assistant](assistant-http-contract.md). Corps d'expérience <=64 KiB,
événement encodé <=32 KiB. La relecture et l'export de faits sont réservés à
l'opérateur CLI dans cette version.

```ts
import { createAssistantClient } from './m3-assistant-client';
const client = createAssistantClient();
// À appeler sur un incident identifié, pas à chaque trame.
const {event, analysis} = await client.recordEvent({
  eventId: crypto.randomUUID(),
  roverId: 'SIMULATED_EXPERIENCE_TEST',
  capturedAt: new Date().toISOString(),
  kind: 'calibration_missing',
  provenance: 'simulated',
  summary: 'Essai simulé : aucune pose caméra fournie.',
}, true);
// Conserver les IDs ; polling tant que queued/running, affichage de failed explicite.
if (analysis) console.log(await client.analysis(analysis.analysisId));
```

Réutiliser le même événement/UUID après une erreur réseau : un nouveau UUID
créerait un autre événement. Le panneau React M3 reste à brancher ; le client
fourni est indépendant de React et ne modifie aucune trame canonique.

## Relecture et récupération de l'ensemble des données

```powershell
python -m crater_assistant export-journal --journal artifacts/experience.sqlite --output artifacts/experience-session.jsonl
python -m crater_assistant review-event EVENT_UUID --journal artifacts/experience.sqlite --reviewer Omar --outcome confirmed --statement "Fait observé et vérifié dans cet essai" --evidence artifacts/test-result.json
python -m crater_assistant export-experiences --journal artifacts/experience.sqlite --output artifacts/reviewed-experiences.md
```

L'export JSONL est un instantané de tous les événements, travaux courants,
tentatives terminées et relectures. Les analyses qu'il contient sont non
vérifiées. Il ne copie pas les images : conserver les médias référencés pour
un transfert complet. Une exportation pendant un travail peut contenir son
état running ; exporter après la fin des travaux pour une session complète.
Les sorties existantes ne sont jamais écrasées.

L'export Markdown retient les faits écrits par l'opérateur dans sa dernière
relecture confirmed, parmi les 100 événements relus les plus récents. Une
relecture rejetée/inconclusive retire l'événement du prochain export. Chaque
confirmation exige des fichiers locaux de preuve explicites (MD/TXT/JSON
<=1 MB) dont les empreintes sont conservées. Une déclaration humaine et un
fichier présent ne prouvent pas automatiquement que le fait est correct :
l'opérateur doit relire la preuve. Aucune réponse LLM n'est promue au corpus.
Chaque segment exporté répète la provenance, les identifiants de l'événement
et de la relecture, les empreintes des preuves et la limite de généralisation.
Ces informations restent avec le fait après le découpage en passages RAG.

Ajouter ensuite le Markdown aux fichiers choisis lors d'une reconstruction
explicite de l'index. Cela enrichit le RAG ; cela ne réentraîne pas le modèle
et ne corrige pas automatiquement la politique du robot.

## Préparation multimodale

**Intégré :** stockage des références d'images, contrôle du chemin, du format,
de la taille et de l'empreinte, association déclarée à un événement.
**Différé :** interprétation des pixels, modèle vision-langage, vidéos/audio,
interface d'affichage des images. `imageAnalysis: not_performed` reste explicite.
Les références seules ne donnent au modèle textuel aucune connaissance du
contenu de l'image. Aucun nouveau poids ni accès cloud n'est nécessaire.

L'étape suivante pourra ajouter un backend vision local après mesures sur le
PC cible : budget GPU partagé avec M1, latence, qualité, abstention et erreurs
d'identification. Les sorties visuelles devront conserver leur provenance et
leurs limites, sans servir seules de preuve d'une position métrique.

## Essai reproductible

Serveur lancé avec journal, Node >=22.18 :

```powershell
node integrations/smoke-experience.mjs http://127.0.0.1:8766 artifacts/new-experience-smoke.json
```

Cet essai utilise un événement explicitement simulé et les modèles texte réels
locaux, via le client M3 et HTTP. Il vérifie la citation de l'événement et la
persistance, puis exige une relecture du contenu. Il ne valide ni ONNX ni la
vision multimodale. Les tests CI utilisent des doubles de modèle explicites.
Résultat local documenté : [validation CPU](validation/experience-local.md).
