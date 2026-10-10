# Corpus scientifique relu pour le RAG local

13 résumés courts en français, vérifiés le 10 octobre 2026 sur les pages
primaires liées dans chaque fichier. Ils servent de contexte scientifique,
pas de données de télémétrie C.R.A.T.E.R. Les limites ajoutées pour notre projet
sont explicitement distinguées des faits décrits par NASA.

- `nasa-autonav.md` : navigation autonome et dangers.
- `nasa-video-cadence.md` : images de conduite espacées d'environ cinq mètres.
- `nasa-pds-calibration.md` : catalogue des produits Navcam calibrés.

| Fiche supplémentaire | Source primaire consultée | Utilité / limite |
|---|---|---|
| [Stéréo](nasa-stereo-cameras.md) | [NASA, composants de Perseverance](https://science.nasa.gov/mission/mars-2020-perseverance/rover-components/) | Navcams/Hazcams ; détection 2D ≠ distance métrique. |
| [Odométrie](nasa-visual-odometry.md) | [JPL Robotics, navigation de Curiosity](https://robotics.jpl.nasa.gov/what-we-do/flight-projects/mars-science-laboratory/surface-system-software-and-rover-navigation/) | Pose et glissement ; suivi d'objets ≠ estimation de pose. |
| [Repères](nasa-spice-frames.md) | [NAIF/JPL, SPICE Frames, 2021](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/frames.html) | Transformations et époque ; origine ENU explicite. |
| [Communications](nasa-dtn-buffering.md) | [NASA, aperçu DTN](https://www.nasa.gov/reference/delay-disruption-tolerant-networking-overview/) | Stocker puis retransmettre ; M2 ne revendique pas la conformité DTN. |
| [Ombres lunaires](esa-lunar-shadows.md) | [ESA, étude PHILIP, 2020](https://www.esa.int/Enabling_Support/Space_Engineering_Technology/Laser-powered_rover_to_explore_Moon_s_dark_shadows) | Soleil bas et énergie ; étude, pas mission déployée. |
| [Essais analogues](esa-rover-field-tests.md) | [ESA, Lucid, 2017](https://www.esa.int/ESA_Multimedia/Images/2017/06/Rover_test_in_darkness) | Essais de jour/nuit ; analogue terrestre ≠ validation lunaire. |
| [Détection](paper-grounding-dino.md) | [Liu et al., Grounding DINO, v5/2024](https://arxiv.org/abs/2303.05499v5) | Fusion texte/image ; scores non transférables au Tiny ONNX M1 sans évaluation. |
| [Confiance](paper-confidence-calibration.md) | [Guo et al., ICML 2017, v2](https://arxiv.org/abs/1706.04599v2) | Calibration probabiliste ; étude de classification, pas calibration de M1. |
| [Suivi](paper-hota-tracking.md) | [Luiten et al., IJCV 2020, v2](https://arxiv.org/abs/2009.07736v2) | Détection/association/localisation image ; pas précision ENU. |
| [Localisation lunaire](paper-lunarnav-localization.md) | [Daftry et al., LunarNav, v1/2023](https://arxiv.org/abs/2301.01350v1) | Carte orbitale ; piste de recherche non intégrée. |

NASA/JPL et ESA sont des sources institutionnelles. arXiv héberge les textes
des auteurs ; un dépôt arXiv n'est pas en soi une certification scientifique.
Les statuts ICML/IJCV sont ceux indiqués dans les notices. Les fiches de
recherche résument les abstracts et notices consultés, sans prétendre à une
revue exhaustive des expériences des articles. Les pages évolutives sans date
de publication explicite sont signalées. `Verified on` est la consultation,
pas la publication. Les versions arXiv sont fixées dans les URL.

Indexer seulement les fichiers choisis, sans ce README :

```powershell
$corpus = Get-Content docs/knowledge/corpus.json -Raw | ConvertFrom-Json
$sources = $corpus.files
python -m crater_assistant index @sources --output artifacts/assistant-research-index.json
python scripts/evaluate_assistant_corpus.py --index artifacts/assistant-research-index.json --output artifacts/assistant-corpus-retrieval.json
python -m crater_assistant ask "Un score de confiance de 0,9 garantit-il 90 % de détections correctes ?" --index artifacts/assistant-research-index.json
python -m crater_assistant serve --index artifacts/assistant-research-index.json --port 8766
```

Les URL `sourceUrl` et dates `verifiedOn` accompagnent chaque passage indexé,
même après découpage. Les citations `[S1]` désignent les passages réellement
retrouvés. Le contrôle accepte les liens HTTPS NASA/ESA et le domaine exact
arxiv.org ; il ne relit pas les pages
pendant une question et ne certifie pas la vérité de chaque phrase du LLM.
Les empreintes du texte local empêchent d'utiliser un index périmé après édition.

Le manifeste sélectionne 16 fichiers : 13 fiches externes et trois documents
internes. L'évaluation utilise le véritable EmbeddingGemma 300M local et vérifie
le passage attendu parmi les quatre premiers pour 13 questions préparées.
Ce n'est ni une précision sur des questions inédites ni une validation factuelle
du LLM. Ces commandes ne téléchargent aucun poids. Consulter manuellement une
URL demande une connexion ; répondre avec le corpus local n'en demande pas.

## Choix des ressources en ligne

L'[API NASA Image and Video Library](https://images.nasa.gov/docs/images.nasa.gov_api_docs.pdf)
permet de rechercher des médias via `/search` et leurs métadonnées. Elle peut
servir à découvrir des ressources pendant la préparation, mais ne fournit pas
le contrat de calibration/pose LOCAL_ENU_V1 de notre rover. Ce corpus retient
des textes relus pour répondre hors ligne. Aucun appel NASA, clé API ou recherche
web automatique n'est ajouté à `/ask`.

L'[API Sentry](https://ssd-api.jpl.nasa.gov/doc/sentry.html) traite les risques
d'impact d'astéroïdes sur Terre et reste hors du périmètre rover. Scraper tout
NASA ajouterait beaucoup de données sans rapport avec nos questions.

Le [catalogue PDS](https://pds.nasa.gov/ds-view/pds/viewBundle.jsp?identifier=urn:nasa:pds:mars2020_navcam_ops_calibrated&version=1.0)
est pertinent pour étudier des produits scientifiques documentés. Une ingestion
PDS complète demande un travail séparé de sélection, lecture des labels et
transformation de repères ; elle ne remplace pas la séquence calibrée M1.

Pour enrichir : choisir une question utile, consulter une source primaire,
résumer sans copier l'article, préciser version/date/limites, ajouter le fichier
et une question de contrôle au manifeste. Reconstruire l'index, vérifier la
recherche et relire quelques réponses et abstentions du véritable LLM local.
Les poids Ollama, indices et documents privés restent locaux.
