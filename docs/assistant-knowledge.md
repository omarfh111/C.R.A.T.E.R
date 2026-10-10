# Repères validés pour expliquer M2

## Calibration et coordonnées

Dans LOCAL_ENU_V1, ENU signifie East, North, Up : x vers l'Est, y vers le Nord,
z vers le haut. Les trois coordonnées sont en mètres et l'origine est le
marqueur convenu au début de la mission.

Une détection M1 donne un pixel de contact dans une image. Un pixel n'est pas
une distance en mètres. Pour projeter ce pixel, M2 utilise la calibration
(fx, fy, cx, cy), le centre de la caméra en mètres et sa rotation vers ENU.
Il construit un rayon puis son intersection avec un plan de sol connu.
La position du rover est fournie séparément par la source ; la calibration
ne permet pas à elle seule de mesurer la position du rover.
Une vidéo NASA sans ces paramètres ne fournit pas des positions ENU métriques.

## Pourquoi des pertes radio peuvent coexister avec une livraison complète

Une trame est une observation unique. Un paquet DATA est une tentative de
transmission : la même trame peut être envoyée plusieurs fois. En cas de perte
DATA ou ACK, M2 réessaie avec la même séquence. La station supprime les doublons.
Il est donc possible de livrer toutes les trames avec des pertes de paquets.
Cela ne garantit pas la livraison : les réessais et la file sont limités ;
une trame peut être abandonnée ou rejetée. Les 30/30 décrivent cet essai seulement.
Une livraison complète ne garantit pas une livraison immédiate : la file et les
coupures peuvent augmenter la latence.

Le taux de livraison des trames est delivered / generated. Le taux de perte DATA
est dataPacketsLost / dataPacketsSent. Le taux de perte ACK est
ackPacketsLost / ackPacketsSent. Ces trois taux ont des dénominateurs différents.
Un rapport mode benchmark mesure une simulation reproductible. Il ne démontre
pas les performances d'une radio physique ou d'une perception sur terrain réel.

## Rôle des modèles

Un embedding représente un document pour retrouver les passages utiles.
Le LLM explique ces passages. Aucun de ces deux modèles ne remplace la
calibration, le calcul géométrique ou la validation du JSON M3. L'assistant
ne décide pas que le rover peut traverser un obstacle.
