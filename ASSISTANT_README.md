# Assistant local et Mission Intelligence

L'assistant facultatif de C.R.A.T.E.R. explique un corpus local avec des passages
sources. Mission Control fournit séparément une intelligence déterministe à
partir des trames WebSocket v1 acceptées : coordonnées ENU, score de détection,
incertitude transmise, ancienneté et compteurs radio. Le LLM ne remplace aucun de
ces calculs, n'ajoute aucun danger et ne pilote pas le rover.

Le [guide Mission Intelligence](docs/mission-intelligence.md) est la référence
actuelle pour le lancement Windows, les performances mesurées, les digests,
les limites de sécurité et la validation. Le [contrat HTTP](docs/assistant-http-contract.md)
décrit les états de disponibilité, concurrence, délai, erreur et abstention.
Le [catalogue du corpus](docs/knowledge/README.md) conserve les sources et leurs
limites scientifiques.

## Lancement facultatif

Le Quick Demo original reste à deux commandes, sans GPU ni Ollama :

```powershell
.\scripts\setup.ps1
.\scripts\start-demo.ps1
```

Après la capture GPU, garder Mission Control ouvert pour examiner les trames et
lancer l'assistant dans une seconde fenêtre. Utiliser l'origine exacte affichée
par le dashboard, port dynamique inclus et sans barre finale ; ce port est un
exemple :

```powershell
.\scripts\start-assistant.ps1 -DashboardOrigin 'http://127.0.0.1:50554'
```

Le lanceur utilise les modèles **déjà installés**
`qwen3:4b-instruct-2507-q4_K_M` et `embeddinggemma:300m`. Le runtime testé est
Ollama 0.40.2 sur RTX 5070 Laptop GPU. Il ne télécharge aucun poids et ne migre
aucun modèle. Le guide détaille le choix NVIDIA, les ports isolés, les options
et la preuve de présence GPU. Le port Ollama partagé 11434 n'est jamais géré
par ce lanceur.

Le premier chargement CUDA a pris environ 110 secondes dans le benchmark :
préparer cette extension en dehors de la démonstration rover de sept minutes.
Le service n'est annoncé prêt qu'après un essai de récupération et génération.
Dans Mission Intelligence, entrer son URL puis sélectionner **CONNECT LOCAL AI**
et **ASK REFERENCES**. Le dashboard fonctionne aussi avec l'assistant désactivé,
absent ou en échec ; aucun démarrage automatique de modèle n'est ajouté au demo.

L'inférence active a sensiblement ralenti M1 dans les essais répétés. L'usage
retenu est **après capture uniquement** : fermer le lanceur avec Ctrl+C avant
une nouvelle capture. Les contrôles de processus du lanceur et du sidecar sont
une protection complémentaire, pas un verrou matériel atomique. Le mode normal
ferme uniquement ses propres arbres de processus Ollama/sidecar. Le mode avancé
`-UseExistingOllama` laisse la durée de vie du runtime sélectionné à l'opérateur.

## Faits M2 sans modèle

La sous-commande `facts` calcule des métriques d'un rapport M2 explicitement
choisi, sans Ollama. Remplacer ce chemin d'exemple par un rapport existant :

```powershell
.\.venv\Scripts\python.exe -m crater_assistant facts 'outputs\demo-replay-EXEMPLE\m2-report.json'
```

Les faits conservent la provenance du rapport et distinguent trames, tentatives
DATA et ACK. Ils ne deviennent pas des mesures live du rover. `ask --report`
et `serve --report` peuvent également joindre des faits calculés d'un rapport
fixé par l'opérateur ; HTTP ne permet pas de choisir un chemin. Le lanceur du
panel n'active pas cette option : les observations courantes se lisent dans
l'inspecteur déterministe de Mission Control.

## CLI et documents sélectionnés

`check`, `index`, `ask`, `warm`, `unload` et `serve` existent pour les essais
locaux. Passer les options globales avant la sous-commande. La CLI conserve
ses valeurs conservatrices (CPU, `keep_alive=0`, contexte 8192, sortie 600,
délai 180 secondes) ; elles ne sont pas les réglages du lanceur GPU. Ne pas
lancer de CLI générative en parallèle d'un autre utilisateur du même runtime,
ni pendant la capture. Utiliser une URL Ollama isolée explicite, par exemple :

```powershell
.\.venv\Scripts\python.exe -m crater_assistant `
  --ollama-url http://127.0.0.1:11435 --gpu `
  --keep-alive 120 --num-ctx 4096 --num-predict 240 --timeout 45 check
```

Cet exemple vérifie les métadonnées installées d'un serveur isolé déjà lancé ;
il ne prouve pas à lui seul l'inférence ou le déport GPU. Pour `serve`, fournir
`--allow-origin` avec l'origine dynamique exacte et `--block-live-m1`. Le guide
et le contrat HTTP détaillent ce chemin ; le lanceur réalise ces réglages sans
modifier de sources ou de `.env`.

Seuls les fichiers explicitement sélectionnés sont lus : Markdown, TXT et JSON,
1 MB maximum par fichier et 1000 passages maximum. Aucun parcours automatique
des dossiers, `.env`, images ou MP4. Le manifeste choisit 13 résumés externes et
trois contrats internes. L'index contient textes, chemins locaux et vecteurs ;
il reste local. Les sources sont reconstruites pour détecter texte, lignes,
empreintes, métadonnées ou extraits de cache altérés. Une modification des
sources ou de l'identité d'embeddings impose de reconstruire l'index.

### Import PDF facultatif

Le corpus livré n'exige pas l'extra PDF. Pour un document explicitement choisi,
installer cet extra dans l'environnement d'intégration, séparé de M1 :

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[assistant]'
.\.venv\Scripts\python.exe -m crater_assistant import-pdf `
  'C:\mission\specification.pdf' --output 'outputs\specification.txt'
```

PDF non chiffré, maximum 50 MB / 200 pages ; texte extrait maximum 1 MB. Les
références de page sont conservées, mais ce n'est pas de l'OCR. Vérifier tableaux,
ordre de lecture et exigences dans le PDF original. Ne pas publier de texte
privé extrait sans examen. Un document est une source de données, jamais une
autorisation d'exécuter ses instructions.

## Intégrité et limites

Les citations identifient les passages réellement retournés et doivent concorder
avec les identifiants déclarés. Les valeurs numériques non soutenues et les
requêtes opérationnelles reconnues peuvent être refusées. Ces contrôles ne
prouvent pas la vérité sémantique d'une phrase. Les explications restent
`unverified_generated`, distinctes des faits déterministes. Les références
NASA/ESA ne certifient pas les performances de notre rover.

Le sidecar HTTP est distinct du WebSocket canonique, lié au loopback, avec
origines explicites, une seule inférence admise, capacités bornées et délai
agrégé. Annuler le client ne garantit pas l'arrêt du modèle. Un timeout met le
sidecar en quarantaine jusqu'au redémarrage sûr ; les observations et le
dashboard continuent de fonctionner. Aucun outil de commande, d'exécution de
code, d'accès Internet documentaire ou d'analyse d'images n'est donné au LLM.

Le journal SQLite d'expérience, l'ingestion automatique d'incidents, le diagnostic
asynchrone et les interfaces multimodales ne sont pas intégrés. Le panneau React
livré couvre l'observation déterministe et les questions scientifiques avec
extraits, citations et limites, sans refonte de Mission Control.

Les [preuves actuelles](docs/validation/mission-intelligence/README.md) et la
[validation navigateur](docs/validation/mission-intelligence-browser.md) détaillent
les essais réellement exécutés. Les anciennes
[traces CPU](docs/validation/assistant-local.json) et le
[plan initial](docs/assistant-plan.md) restent historiques ; leurs versions,
temps, commandes et nombres de tests ne décrivent pas le runtime actuel.
Les contrôles CI ordinaires restent sans modèle, GPU ni identifiant cloud.
