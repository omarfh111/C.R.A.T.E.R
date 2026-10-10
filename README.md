# C.R.A.T.E.R. - M1 : perception et tracking

Branche `feat/ai-perception`. Python 3.11+, traitement local, sans API cloud
pendant l'inference. Les coordonnees metriques et le reseau appartiennent a M2.

## Installation

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
# CPU (installation validee localement) :
.\.venv\Scripts\python -m pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cpu
# Option RTX 3050 (pilote compatible CUDA 12.8, performance a mesurer) :
.\.venv\Scripts\python -m pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python -m pip install transformers==4.57.1
.\.venv\Scripts\python -m crater_m1 download-model
.\.venv\Scripts\python -m pytest
```

Le telechargement des poids est une etape explicite de preparation. `run`
utilise uniquement le cache local ; aucune connexion n'est necessaire.

## Video NASA

```powershell
.\.venv\Scripts\python -m crater_m1 inspect ..\vid3.mp4
.\.venv\Scripts\python -m crater_m1 run ..\vid3.mp4 --view left --device auto --output outputs/nasa-run
```

`vid3.mp4` : First AutoNav, deux vues 1280x960 cote a cote, 43 images, 2 FPS.
`vid2.mp4` : Long Autonomous Drive, 53 images, 5 FPS de lecture.
`vid1.mp4` : simulation avec rover visible, 640x360, 1367 images.
Les noms correspondent aux fichiers examines dans le dossier utilisateur.
Les videos ne sont pas versionnees. Une seule vue est analysee pour eviter
la duplication stereo. Le temps video ne mesure pas le temps original du rover.

Sorties : `observations.jsonl`, `metrics.json`, `preview.mp4`, images annotees.
Choisir un nouveau dossier pour chaque essai. Les detections reelles restent
en pixels ; camera et pose sont nulles si inconnues.

## Scene controlee pour M2 et tests

```powershell
.\.venv\Scripts\python -m crater_m1 simulate --output outputs/scene
.\.venv\Scripts\python -m crater_m1 run outputs/scene/scene.mp4 --backend synthetic-contrast --calibration outputs/scene/calibration.json --output outputs/scene-run
.\.venv\Scripts\python -m crater_m1 evaluate outputs/scene-run/observations.jsonl outputs/scene/annotations.json --output outputs/scene-run/accuracy.json
```

Le backend `synthetic-contrast` analyse vraiment les pixels de silhouettes
sombres. Il est uniquement destine a cette scene controlee : ce n'est pas un
modele IA valide sur NASA. Sa confiance 0.7 est heuristique et constante.
Le detecteur ne lit jamais les annotations ni les positions de reference.

## Mesures et limites

- Grounding DINO Tiny, prompt `a rock.`, seuil configurable et NMS.
- Tracking : IoU + affectation hongroise, compensation affine ORB/RANSAC,
  pistes perdues expirees apres trois images. Pas de garantie d'identite apres
  grand changement de point de vue ; aucun suivi 3D/reidentification.
- `evaluate` : precision/rappel a IoU 0.5 et changements d'identifiant sur les
  images annotees. Pas de faux score IDF1/MOTA ; le perimetre est dans `scope`.
- Mesures : FPS de traitement, FPS bout en bout, latence moyenne/p95, RSS,
  temps et utilisation CPU, memoire GPU allouee. Chargement modele exclu,
  premiere inference incluse ; encodage preview exclu de la latence traitement.
- Aucun seuil FPS officiel chiffre n'est impose. La performance doit etre
  mesuree sur la machine de demo ; FPS de lecture != FPS d'inference.
- Le milieu bas d'une boite est une approximation du contact au sol.
  La calibration est necessaire pour M2 ; cratere/slope ne sont pas revendiques
  comme detectes tant qu'ils n'ont pas ete verifies.

Contrat : `docs/m1-contract.md`. Tests : `tests/m1/`.
Sources : [NASA First AutoNav](https://science.nasa.gov/resource/perseverances-first-autonav-drive/),
[NASA Long Drive](https://science.nasa.gov/resource/perseverance-rover-camera-view-of-long-autonomous-drive/),
[Grounding DINO](https://huggingface.co/IDEA-Research/grounding-dino-tiny).

## Integration et preuve hors ligne

Voir `docs/m1-integration.md` pour M2, les tests reseau et le callback Python.
Un test optionnel interdit toute connexion socket pendant le chargement et
l'inference du modele local : apres telechargement, definir
`CRATER_AI_SMOKE=1` puis `python -m pytest tests/m1/test_ai_offline.py`.

Les annotations pilotes dans `examples/nasa-pilot-annotations.json` portent
sur trois images NASA et un seuil de taille explicite. Le SHA256 de la video
est controle avant evaluation. Ce petit jeu manuel ne permet pas de generaliser
les performances a toute une mission lunaire.

## Hosted Hugging Face experiment

See `docs/m1-hosted.md` for the selected hosted grounding model, lightweight
installation, fine-grained token permissions and smoke test. Select
`--backend hf-hosted` explicitly. This remote mode is marked CLOUD in preview
and reports; it does not satisfy the challenge's local-only perception rule.

## Free Hugging Face Space experiment

A live-tested free Grounding DINO Base Space is available through
`--backend hf-space`. See [setup, quota and quality limits](docs/m1-free-hf.md).
No model weights or GPU are required locally. The current `.env` token works.

```powershell
.\.venv\Scripts\python -m pip install -r requirements-m1-spaces.txt
.\.venv\Scripts\python -m crater_m1 run ..\vid3.mp4 --backend hf-space --view left --stride 10 --max-frames 3 --output outputs/nasa-free-pilot
```

This experimental cloud mode remains subject to queues/daily quotas and the
challenge's local-perception restriction. It emits normal tracked JSONL,
preview and measured metrics for M1; it does not invent 3D coordinates.
