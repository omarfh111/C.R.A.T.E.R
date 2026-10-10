# M2 : localisation et communication

## Périmètre autorisé

Construire M2 sur une branche séparée, vérifier chaque étape puis commit/push.
Le détecteur M1 et le dashboard M3 restent des composants externes. L'assistant
LLM/RAG est un bonus ultérieur, indépendant du transport et des calculs spatiaux.

## Contrat M3

Source : `feat/mission-control`, contrat `a03880f5a6108e477283154bfc49027a40d9cb81`.
https://github.com/omarfh111/C.R.A.T.E.R/blob/feat/mission-control/docs/telemetry-contract.md

Le JSON canonique v1 est conservé sans nouveaux champs. WebSocket local :
`ws://127.0.0.1:8765/telemetry`, un objet JSON par message texte. Origine :
marqueur convenu au début de la mission ; `LOCAL_ENU_V1` : x Est, y Nord, z Haut,
mètres. Capture et observation sont UTC ; la réception appartient au dashboard.
Les séquences croissent par rover ; une retransmission conserve la séquence.
Les compteurs du JSON sont un instantané à la capture, non à la réception.

## Architecture

Package Python `crater_m2`, indépendant des fichiers React de M3 :
géométrie -> JSON canonique -> binaire -> simulateur radio -> décodage -> WS.
Le simulateur est un script de transport à événements, conforme au format
logiciel imposé ; il n'impose pas UDP et mesure les octets applicatifs seulement.
Une liaison partagée sérialise données et ACK selon le débit ; pertes et délais
dans les deux directions, coupures configurables, graine reproductible.
Stop-and-wait et file FIFO bornée conservent l'ordre attendu par M3. Les ACK perdus
provoquent des doublons radio supprimés à la station. Après limite d'essais,
le paquet est abandonné avec une métrique explicite ; file pleine : refus du
nouveau paquet. Un blackout conserve la file, sans diffuser de fausses réceptions.

## Localisation

Caméra pinhole rectifiée : fx/fy/cx/cy, résolution, centre ENU et rotation
caméra-vers-ENU connus. Axes caméra : x droite, y bas, z avant.
Un pixel de contact produit un rayon ; intersection avec le plan z=ground_z_m.
Refuser les rayons parallèles, derrière la caméra ou hors portée et les pixels
invalides. Pour un rover mobile, la pose doit être fournie à chaque observation.
Un rayon ne mesure pas la hauteur d'un obstacle ni la profondeur d'un cratère.
L'incertitude est une estimation documentée basée sur perturbation du pixel et
incertitude de pose, pas une probabilité garantie ou un substitut à calibration.

Un petit scénario calibré produit des pixels à partir de points ENU connus.
La reconstruction utilise seulement ces pixels et la caméra ; la vérité terrain
est utilisée uniquement pour validation. Ce scénario n'est pas un détecteur IA
et les vidéos NASA non calibrées ne sont pas déclarées localisées en mètres.
Entrée M1 : JSONL avec pose caméra, position rover et détections (id stable,
type, boîte ou pixel de contact, confiance, observation UTC).

## Binaire v1

Big endian, magic/version, IDs UTF-8, séquence uint32, horodatages millisecondes
UTC uint64, positions int32 millimètres, incertitudes uint32 millimètres arrondies
vers le haut, confiance uint16. Types/statuts : enums ; CRC32 sur le paquet.
Le CRC détecte les corruptions, sans authentifier l'expéditeur.
Refuser débordement, NaN/inf, paquets tronqués, champs inconnus et données invalides.
La quantification entraîne <=0,5 mm par axe et <=1/(2*65535) sur la confiance.
IDs : 1..255 octets ; taille de paquet plafonnée à 65507 octets. Les paquets sont
autoportants, sans dictionnaire caché à synchroniser après blackout.

## Vérification et livraison

Tests de projection/reconstruction contre repères connus, transformations ENU,
entrées invalides ; tests de round-trip/corruption du codec ; tests de débit réel
en octets, pertes/ACK, timeout et coupure/reprise ; vrai client WebSocket local.
Validation croisée avec le parser Zod réel de M3, sans modifier sa branche.
Démo en une commande, rapport de mesures, documentation d'intégration et CI.
Chaque lot fonctionnel passe les tests avant commit et push vers la branche M2.
