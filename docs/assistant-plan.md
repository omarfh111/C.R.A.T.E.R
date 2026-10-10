# Assistant local M2 — plan autorisé

Omar demande de poursuivre LLM, embeddings et RAG pendant que M1 termine.
Cette autorisation couvre l'implémentation, la validation, les commits et le push
sur `feat/spatial-telemetry`. L'assistant ne dépend pas des nouveaux backends M1.

1. Tests avant code : transport Ollama local, corpus explicite, index et citations.
2. Retriever : EmbeddingGemma 300M, documents Markdown/TXT/JSON locaux choisis
   explicitement, index JSON versionné, recherche cosinus, sources avec lignes.
3. Analyste : faits déterministes des rapports M2, distinction DATA/ACK/trames.
4. Explicateur : Qwen3 4B Instruct 2507 local, texte français avec citations ;
   Python construit la réponse JSON canonique de l'assistant.
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

## Préparation de l'intégration M3

Sources NASA relues et datées dans `docs/knowledge`, métadonnées sourceUrl et
verifiedOn conservées par le RAG. Les index existants restent compatibles.
Le client TypeScript et le contrat HTTP sont livrés séparément du dashboard,
avec tests Node, types stricts et test réel HTTP à backend déterministe.
Voir `docs/assistant-http-contract.md` pour démarrage et smoke local Ollama.
L'API NASA de médias est une ressource de découverte, pas une dépendance de
`/ask` ; aucune clé ni connexion NASA n'est nécessaire pendant la démo.

Attendent M1 : analyse automatique d'images/vidéos, index multimodal des obstacles,
évaluation sur sorties finales de perception et données réelles calibrées.
Attendent M3 : intégration du panneau assistant dans son dashboard ; l'API est
documentée pour cela. Le schéma canonique de télémétrie reste inchangé.

## Validation locale

- EmbeddingGemma 300M : installé, 11 passages M2 indexés en CPU.
- EmbeddingGemma 2:270m : catalogue confirmé, pull refusé par Ollama 0.17.1
  avec HTTP 412 (runtime trop ancien). Migration configurée, pas annoncée validée.
- Premiers essais Qwen : réponses approximatives ou tronquées, pas une
  comparaison de performance équitable entre modèles.
- Qwen3:4b : les métadonnées locales identifient Thinking 2507, incompatible
  avec un mode sans raisonnement ; ces poids sont refusés par le client.
- Qwen3:4b-instruct-2507-q4_K_M : installé, sous Apache 2.0 ; génération directe
  sans raisonnement. Calibration, rapport radio et abstention vérifiés en CPU
  avec relecture des réponses ; voir docs/validation/assistant-local.json.
- Suite complète : 183 réussis, 1 smoke optionnel ignoré ; 44 tests assistant.
- Temps CPU observés : 65/128/61 s, chargements inclus ; le second essai partage
  le CPU avec pytest. Trois exemples, pas une garantie générale de factualité.
- PDF fourni : 11 pages exportées avec références conservées, sans publier le texte.
- Revue indépendante : aucun défaut bloquant ; lecture unique des rapports et
  préfixes de page sur lignes PDF longues corrigés avec tests de régression.
- M1 nouveau head a6df2e6 : ONNX GPU local et réglage des seuils, sans changement
  de schema.py/pipeline.py dans le diff observé ; pas fusionné pendant son travail.
