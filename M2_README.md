# M2 - Localisation et télémétrie C.R.A.T.E.R.

M2 reçoit les détections de M1, calcule leurs positions dans `LOCAL_ENU_V1`,
encode un message binaire, simule son transport radio, puis expose le JSON
canonique attendu par M3 sur `ws://127.0.0.1:8765/telemetry`.

## Installation (Python 3.11 ou 3.12)

Depuis la racine du dépôt, sous PowerShell :

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
.\.venv\Scripts\python.exe -m pytest -q
```

Linux/macOS : `python3 -m venv .venv`, puis `.venv/bin/python -m pip install -e '.[test]'`.
La branche intègre également le package M1. Pour la suite complète, installer
`.[test,hosted]` et définir `CRATER_M2_SOURCE` à la racine du checkout, comme
indiqué dans le README principal. Aucun téléchargement de modèle IA ni
service cloud nécessaire pour la démo contrôlée. Les tests utilisent de vrais sockets localhost.

## Démo live pour M3

```powershell
.\.venv\Scripts\python.exe -m crater_m2 --duration 120 --bandwidth 512
```

Dans le checkout du dashboard de M3, mettre dans `.env.local` :

```dotenv
VITE_TELEMETRY_MODE=LIVE
VITE_TELEMETRY_WS_URL=ws://127.0.0.1:8765/telemetry
```

Redémarrer Vite et ouvrir Mission Control. La station ne diffuse que les
observations réellement décodées après leur passage par le simulateur radio.
Une coupure par défaut de 8 à 14 secondes permet de voir le vieillissement des
informations et la reprise. Les statuts contenus dans les paquets sont ceux
de leur capture : un ancien statut `disconnected` peut arriver après la reprise.
M3 détermine séparément l'état de sa connexion à la station.

Les séquences repartent de zéro à chaque nouvelle exécution. Pour conserver
l'état du dashboard entre deux exécutions, passer `--start-sequence N`, avec N
strictement supérieur à la dernière séquence reçue. Sinon recharger le dashboard.
Une reconnexion pendant la même mission reçoit le dernier paquet reçu par la
station, avec sa séquence et ses horodatages originaux, sans prétendre qu'il est frais.

## Benchmark reproductible et résultats

```powershell
.\.venv\Scripts\python.exe -m crater_m2 --benchmark --duration 30
```

Le temps radio est simulé : le benchmark peut terminer en moins d'une seconde
alors que les observations représentent 30 secondes et la file se vide ensuite.
Les captures sont UTC ; seule la graine et les temps relatifs déterminent les
pertes. Le mode live utilise les mêmes événements mais attend le temps réel.

Sorties locales (non commitées) :

- `artifacts/m2-report.json` : débit, octets DATA/ACK, pertes, retransmissions,
  délais, abandon, file et erreur spatiale.
- `artifacts/received-frames.jsonl` : JSON canoniques décodés, un par ligne.

Résultat mesuré le 10 octobre 2026, graine 7, source synthétique calibrée :

| Mesure | Résultat |
|---|---:|
| Débit partagé DATA + ACK | 256 octets/s |
| Probabilité de perte, chaque sens | 20 % |
| Coupure | 8-14 s |
| Trames produites / livrées / acquittées | 30 / 30 / 30 |
| Taille binaire par trame, 3 dangers | 163 octets |
| Taille JSON moyenne | environ 976 octets |
| Octets radio totaux, retransmissions + ACK compris | 8709 |
| Retransmissions / doublons radio supprimés | 21 / 6 |
| Délai de livraison moyen / maximal | 16,16 s / 29,09 s |
| Erreur spatiale maximale après décodage | environ 2,32 cm |
| Fin de livraison + ACK | 58,14 s simulées |

La taille binaire baisse d'environ 83 % par rapport au JSON. Avec retransmissions
et ACK, le coût total représente environ 30 % du JSON initial transmis une seule
fois, pour ce scénario où toutes les trames sont livrées. Ce résultat ne garantit
pas un taux de livraison universel : les pertes, la file et les limites d'essais
doivent être indiquées. Le faible débit provoque ici des données anciennes ; il
ne suffit pas de livrer les messages pour qu'ils soient immédiatement utilisables.

Les octets mesurés sont ceux du protocole applicatif simulé, CRC inclus. Ils
n'incluent pas les en-têtes TCP/IP/WebSocket du lien station-dashboard, et ne
représentent pas la consommation d'une radio physique.

## Brancher M1

### Analyse vidéo et télémétrie dans la même exécution

```powershell
python -m crater_m1 simulate --frames 30 --output outputs/live-scene
python -m crater_m2 --perception-video outputs/live-scene/scene.mp4 --calibration outputs/live-scene/calibration.json --perception-backend synthetic-contrast --perception-output outputs/m1-live-run --duration 30 --bandwidth 512
```

M1 analyse les pixels dans un worker local et transmet chaque observation par
callback. La station continue à traiter radio et WebSocket pendant l'inférence.
La file intermédiaire contient quatre observations au maximum, configurable par
`--perception-buffer` ; lorsqu'elle est pleine, le callback attend et ralentit M1.
`--fps` limite leur prise en charge par M2, sans remplacer leurs heures de capture.
Le statut et les compteurs DATA sont reconstruits à l'heure de capture à partir
de l'historique du simulateur, même si l'inférence termine pendant une coupure.
Les pertes du simulateur sont connues par construction ; ce n'est pas un
estimateur de pertes pour une radio physique.

Pour Grounding DINO local, installer `.[ai]`, préparer les poids avec la commande
M1 `download-model`, puis retirer `--perception-backend synthetic-contrast` et
fournir une vidéo et une calibration réelles compatibles. Aucun backend cloud
n'est proposé par cette commande d'intégration. Le modèle suit le cache local.

`--duration` inclut le chargement du modèle : prévoir une durée adaptée, par
exemple 120 secondes pour un premier essai. Zéro observation donne un rapport
incomplet et le code de sortie 2. Une erreur M1 donne un échec explicite, y compris
si elle survient lors de l'arrêt. L'arrêt attend la fin de l'inférence en cours,
puis interrompt le prochain callback ; il ne peut pas interrompre une opération
native bloquée. Les observations restantes à la limite sont comptées dans
`source.discardedAtStop`. Les écritures M1 partielles peuvent ne pas avoir de
`metrics.json` si la mission interrompt son callback avant la fin de la vidéo.
Choisir des répertoires de sortie distincts et un nouveau répertoire M1 par essai.

### Relecture d'un fichier déjà produit

```powershell
.\.venv\Scripts\python.exe -m crater_m2 --input examples/m1-observations.jsonl --no-blackout --loss 0
```

Lire [le contrat d'entrée M1](docs/m1-observation-contract.md). Les trois exemples
sont enregistrés avec des horodatages fixes : M3 peut donc les signaler anciens.
Pour une vraie mission, M1 fournit l'heure de capture réelle et la pose calibrée
de la caméra à cet instant. Le fichier est lu progressivement, pas entièrement
chargé en mémoire. `--fps` règle la cadence de lecture, sans changer les horodatages.

Détections invalides : rejetées individuellement avec une raison dans le rapport.
Calibration absente/invalide : erreur explicite, aucune coordonnée inventée.

## Hypothèses et limites

- Origine = marqueur de départ convenu avec M3 ; x Est, y Nord, z Haut, mètres.
- Caméra pinhole déjà rectifiée et pose connue ; sol supposé plan et connu.
- On localise le contact au sol ou un point représentatif d'un danger.
- `z=0` n'est pas une mesure de hauteur du rocher ou de profondeur d'un cratère.
- Incertitude = perturbations de pixel plus budget de pose ; aucune garantie
  lorsque les hypothèses de terrain/calibration sont fausses.
- Les pixels de démo sont synthétiques, avec bruit ; les positions de référence
  servent uniquement à évaluer les calculs. Ce module n'est pas un détecteur IA.
- Les MP4 NASA/ESA fournis ne sont pas annoncés comme calibrés par ce prototype.
- LLM/RAG reste un bonus à intégrer à Mission Control après le MVP ; il n'intervient
  pas dans la localisation, la fiabilité ou les décisions du transport.

## Transport et robustesse

Script radio à événements avec débit réellement proportionnel aux octets,
latence/jitter, pertes et coupures dans les deux sens. Médium partagé, FIFO
stop-and-wait, temporisation adaptée au temps DATA+ACK, retransmissions avec
séquence inchangée. Les doublons radio sont acquittés mais publiés une seule fois.

La file contient au maximum 64 paquets (configurable). Si elle est pleine, le
nouveau paquet est refusé et compté. Après 20 essais, abandon explicite ; aucun
mécanisme ne promet une livraison pendant une coupure illimitée. Un dépassement
du temps de vidage laisse une file non vide dans le rapport et renvoie le code 2.

Le bridge est limité à localhost. Les clients lents ont une file bornée et sont
déconnectés avec le code 1013 ; leur lenteur ne bloque pas le simulateur radio.
CRC32 détecte les corruptions ; ce n'est ni une signature ni une authentification.
M2 agrège les latences, erreurs et tailles sans conserver tous les échantillons.
Les détails de rejet sont limités à 100 par défaut (`--rejection-samples`) ;
`source.rejectedDetections` reste le total, et `rejectedDetectionsOmitted` indique
les détails omis. L'historique radio est limité à 4096 tentatives DATA
(`--link-history`) ; ses instantanés conservent les compteurs cumulatifs complets.
Une capture antérieure à l'historique disponible provoque un échec explicite,
avec un rapport incomplet, au lieu de recevoir des compteurs inventés. Augmenter
la limite lorsque l'inférence ou le tampon produit un retard important.
Ces limites concernent M2 ; les ressources et statistiques internes de M1
dépendent de son backend. Les journaux JSONL sur disque croissent avec la mission.

## Validation avec le code de M3

```text
node scripts/validate-m3-contract.mjs CHEMIN_M3/src/telemetry/contract.ts artifacts/received-frames.jsonl
```

Node >=22.18 et les dépendances npm de M3 sont nécessaires. Le script importe
le vrai parser Zod de M3, sans reproduire approximativement ses règles. La CI
teste Python 3.11/3.12 et compare les messages au commit M3
`2015192b51ed1b4485faff1fa48bff5442cb3c82`. Mettre à jour cette référence lorsque
le contrat partagé évolue, après accord entre M2 et M3.

Le schéma M3 n'a pas changé. Documentation technique :
[binaire](docs/m2-binary-protocol.md), [conception](docs/m2-design.md).
