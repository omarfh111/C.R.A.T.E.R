# Integration M1 avec M2

Validation contre M2 commit `c4e42964ebd9f4c36a935e004d4ca2a7ec46e95b`.
M1 ne modifie pas la branche M2 ni la branche M3.

1. Mettre `crater_m1` et `crater_m2` dans le meme checkout lors de l'integration.
2. Installer les dependances M1 via `requirements-m1.txt`, ainsi que celles
   de M2 et le couple torch/torchvision approprie. Les deux branches ajoutent
   un `pyproject.toml` : fusionner les dependances et points d'entree avec M3,
   plutot que d'ecraser le fichier d'un autre membre.
3. Generer une scene avec `python -m crater_m1 simulate --output outputs/scene`.
4. Executer M1 : `python -m crater_m1 run outputs/scene/scene.mp4 --backend synthetic-contrast --calibration outputs/scene/calibration.json --output outputs/m1-run`.
5. Executer M2 : `python -m crater_m2 --input outputs/m1-run/observations.jsonl --fps 1 --duration 90 --drain 300 --queue 128`.
6. M3 se connecte a `ws://127.0.0.1:8765/telemetry` selon le contrat M2.

Pour un test reproductible sans attendre les delais reels, ajouter `--benchmark`
a M2. Cela teste le reseau en temps virtuel, sans ouvrir le serveur WebSocket.
Le rapport M2 dans `docs/validation/m1-m2-radio.json` vient de ce mode : il
ne prouve pas a lui seul l'affichage du dashboard ni un traitement live.

Pour verifier le contrat depuis un autre checkout M2, definir
`CRATER_M2_SOURCE` a son chemin absolu puis lancer `python -m pytest tests/m1`.
Le test d'integration passe les detections extraites de vrais pixels simules
au code `observation_to_frame` de M2 et compare aux positions connues.
Les annotations ne sont jamais fournies au detecteur.

Les timestamps NASA sont ceux de l'acquisition pour la demo locale : les
videos historiques n'exposent pas une horloge de capture exploitable. Le
JSONL permet la relecture ; `crater_m1.pipeline.run(..., on_observation=callback)`
livre egalement chaque observation pendant l'analyse. M2 peut appeler
`observation_to_frame` dans ce callback puis alimenter sa file radio. Le callback
est synchrone : un consommateur lent ralentit M1. La latence mesuree inclut ce
cout quand un callback est installe. Le lecteur CLI actuel de M2 consomme un
fichier deja disponible, sans lecture suivie (tail).

Sur la branche d'intégration `feat/spatial-telemetry`, M2 fournit aussi
`--perception-video` avec `--calibration` pour lancer le callback M1 et le
transport radio ensemble, sans relecture du JSONL. Voir `M2_README.md` pour
la commande, la file bornée, les limites d'arrêt et la durée de mission.
