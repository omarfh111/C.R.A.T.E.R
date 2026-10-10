# Corpus NASA relu pour le RAG local

Trois résumés courts en français, vérifiés le 10 octobre 2026 sur les pages
officielles liées dans chaque fichier. Ils servent de contexte scientifique,
pas de données de télémétrie C.R.A.T.E.R. Les limites ajoutées pour notre projet
sont explicitement distinguées des faits décrits par NASA.

- `nasa-autonav.md` : navigation autonome et dangers.
- `nasa-video-cadence.md` : images de conduite espacées d'environ cinq mètres.
- `nasa-pds-calibration.md` : catalogue des produits Navcam calibrés.

Indexer seulement les fichiers choisis, sans ce README :

```powershell
python -m crater_assistant index docs/assistant-knowledge.md docs/m1-observation-contract.md docs/m2-design.md docs/knowledge/nasa-autonav.md docs/knowledge/nasa-video-cadence.md docs/knowledge/nasa-pds-calibration.md --output artifacts/assistant-nasa-index.json
python -m crater_assistant ask "Pourquoi le FPS de lecture de la vidéo NASA ne représente-t-il pas la cadence de capture ?" --index artifacts/assistant-nasa-index.json
```

Les URL `sourceUrl` et dates `verifiedOn` accompagnent chaque passage indexé,
même après découpage. Les citations `[S1]` désignent les passages réellement
retrouvés. Le contrôle accepte les liens HTTPS NASA ; il ne relit pas les pages
pendant une question et ne certifie pas la vérité de chaque phrase du LLM.
Les empreintes du texte local empêchent d'utiliser un index périmé après édition.

## Choix des ressources en ligne

L'[API NASA Image and Video Library](https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf)
permet de rechercher des médias via `/search` et leurs métadonnées. Elle peut
servir à découvrir des ressources pendant la préparation, mais ne fournit pas
le contrat de calibration/pose LOCAL_ENU_V1 de notre rover. Ce corpus retient
des textes relus pour répondre hors ligne. Aucun appel NASA, clé API ou recherche
web automatique n'est ajouté à `/ask`.

Le [catalogue PDS](https://pds.nasa.gov/ds-view/pds/viewBundle.jsp?identifier=urn:nasa:pds:mars2020_navcam_ops_calibrated&version=1.0)
est pertinent pour étudier des produits scientifiques documentés. Une ingestion
PDS complète demande un travail séparé de sélection, lecture des labels et
transformation de repères ; elle ne remplace pas la séquence calibrée M1.

Pour mettre à jour le corpus : relire la page officielle, corriger le résumé,
mettre à jour `Verified on`, reconstruire l'index et refaire les essais de
réponse/abstention. Les poids Ollama, indices et documents privés restent locaux.
