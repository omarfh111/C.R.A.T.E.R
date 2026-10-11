# Validation du journal et du diagnostic local — 11 octobre 2026

Preuve : [résultat JSON](experience-local.json). Le test s'est terminé le
10 octobre à 23:56 UTC, soit le 11 octobre à 00:56 en Tunisie.

Un incident explicitement **simulé**, sans pose caméra, a été enregistré par
le client TypeScript M3 via HTTP réel. Le serveur a utilisé les modèles locaux
Ollama `embeddinggemma:300m` et `qwen3:4b-instruct-2507-q4_K_M` sur CPU,
avec le corpus hors ligne de 24 passages. Aucun appel d'inférence cloud.

| Mesure | Résultat de cet essai |
| --- | --- |
| Acceptation de l'événement et du travail | 38,6 ms |
| Attente totale jusqu'au résultat reçu | 104,1 s |
| État final | completed, tentative 1 |
| Citation de l'événement | S5, avec empreinte et UUID |
| Interprétation d'image | not_performed |

La durée totale inclut l'attente du modèle local et le polling ; elle ne
mesure pas le débit de perception M1. Cet exemple ne constitue pas un
benchmark général et justifie le traitement asynchrone des incidents.

La réponse a été relue : elle identifie la pose caméra absente et refuse une
position ENU fiable pour cet événement. Elle cite les documents techniques et
l'observation fournie ; elle n'invente aucune coordonnée. Les phrases portant
sur l'absence de localisation s'appliquent à cet événement, pas à toutes les
capacités du rover. Cette relecture ne certifie pas les futures réponses.

L'export CLI de la base après arrêt du serveur contient un événement, un
travail completed et sa tentative completed. Les analyses restent explicitement
non vérifiées dans cet export ; aucun fait n'a été ajouté automatiquement au RAG.

Vérifications locales : **285 tests Python réussis, 3 ignorés**, **9 tests du
client TypeScript réussis**, compilation TypeScript stricte réussie. Elles
couvrent journal, worker, reprise, saturation, erreurs, contexte volumineux,
HTTP et export. La CI utilise des doubles de modèle,
distincts de cet essai Ollama réel. Voir le guide
[d'intégration](../experience-integration.md) pour reproduire l'essai.

Le producteur d'incidents et son affichage doivent encore être raccordés à M3.
L'essai GPU ONNX sur séquence calibrée reste à réaliser sur le PC M1.
La préparation multimodale vérifie des références d'images ; aucun modèle
vision-langage, raisonnement sur pixels ou commande moteur n'est intégré ici.
