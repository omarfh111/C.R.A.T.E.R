# Assistant local M2 — plan autorisé

Omar demande de poursuivre LLM, embeddings et RAG pendant que M1 termine.
Cette autorisation couvre l'implémentation, la validation, les commits et le push
sur `feat/spatial-telemetry`. L'assistant ne dépend pas des nouveaux backends M1.

1. Tests avant code : transport Ollama local, corpus explicite, index et citations.
2. Retriever : EmbeddingGemma 300M, documents Markdown/TXT/JSON locaux choisis
   explicitement, index JSON versionné, recherche cosinus, sources avec lignes.
3. Analyste : faits déterministes des rapports M2, distinction DATA/ACK/trames.
4. Explicateur : Qwen3 4B local, réponse française structurée avec sources.
5. Vérificateur : citations connues, abstention si aucune citation valide. Cela
   ne prouve pas que chaque phrase générée est vraie ; garder les sources visibles.
6. CLI et API HTTP locale distinctes de la télémétrie M3. Pas d'outil de commande,
   d'accès internet runtime ou d'exécution des instructions des documents.
7. Tests sans modèles en CI, smoke réel Ollama sur cette machine, revue et push.
8. Import PDF optionnel avec références de page pour la spécification fournie,
   sans indexer de fichiers non sélectionnés ni publier son texte extrait.

Les rôles forment une chaîne contrôlée, pas des agents autonomes. Aucun besoin de
framework multi-agent ou d'API payante pour ce périmètre. Le client refuse les
modèles cloud et vérifie les métadonnées Ollama avant l'inférence ; CPU par défaut
pour laisser la VRAM à M1, modèles déchargés après chaque appel.

Attendent M1 : analyse automatique d'images/vidéos, index multimodal des obstacles,
évaluation sur sorties finales de perception et données réelles calibrées.
Attendent M3 : intégration du panneau assistant dans son dashboard ; l'API est
documentée pour cela. Le schéma canonique de télémétrie reste inchangé.

## Validation en cours

- EmbeddingGemma300M : installé,11passages M2 indexés en CPU.
- EmbeddingGemma2:270m : catalogue confirmé, pull refusé par Ollama0.17.1
  avec HTTP412 (runtime trop ancien). Migration configurée, pas annoncée validée.
- Qwen3:1.7b : inférence réelle testée mais explications trop approximatives ;
  citations parfois absentes. Non retenu comme recommandation finale.
- Qwen3:4b : téléchargement pour essai comparatif, sous Apache2.0.
- PDF fourni :11pages exportées avec références conservées, sans publier le texte.
- Revue indépendante : aucun défaut bloquant ; lecture unique des rapports et
  préfixes de page sur lignes PDF longues corrigés avec tests de régression.
- M1 nouveau head a6df2e6 : ONNX GPU local et réglage des seuils, sans changement
  de schema.py/pipeline.py dans le diff observé ; pas fusionné pendant son travail.
