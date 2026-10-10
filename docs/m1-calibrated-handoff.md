# Partager la validation calibrée M1

M1 est figé à `94bcf577e0aa5e8f9310d3fadc62757b26ce657b`. Ses sources finales
et son rapport sont intégrés dans `feat/spatial-telemetry`. Les fichiers du run
ONNX restent sur le PC M1 : cette procédure se réalise depuis ce PC, avec ses
artefacts existants. Elle ne relance pas le modèle et ne télécharge aucun poids.

## Export vérifié des petits fichiers

Utiliser le checkout M2 séparé décrit dans `m1-m2-onnx-integration.md`. Le mettre
à jour sur la dernière branche M2 seulement après vérification d'un état propre.
Ces commandes refusent de changer de révision si des fichiers locaux sont modifiés.

```powershell
Set-Location D:\space_esb_m2
if (git status --porcelain) { throw 'Le checkout M2 doit être propre avant sa mise à jour.' }
git fetch origin feat/spatial-telemetry
if ($LASTEXITCODE -ne 0) { throw 'Échec du fetch.' }
git switch --detach origin/feat/spatial-telemetry
if ($LASTEXITCODE -ne 0) { throw 'Échec du changement de révision.' }
$m1Python = 'D:\space_esb_m1\.venv\Scripts\python.exe'
$scene = 'D:\space_esb_m1\outputs\m1-final-scene'
$run = 'D:\space_esb_m1\outputs\m1-final-onnx'
$bundle = 'examples/m1-onnx-calibrated'
& $m1Python -m crater_m2.handoff --scene $scene --run $run --output $bundle
if ($LASTEXITCODE -ne 0) { throw 'Export refusé : corriger les fichiers source indiqués.' }
```

Adapter les chemins si les artefacts sont ailleurs. L'export refuse un dossier
existant et vérifie : modèle ONNX et révision convenus déclarés avec DirectML,
empreinte de la vidéo dans les annotations/métriques/observations, nombre de
trames, indices uniques et chronologiques, cohérence caméra/pose/calibration,
projection M2 sans rejet et couverture des annotations.

Le dossier contient les octets originaux de `observations.jsonl`, `calibration.json`,
`annotations.json`, `metrics.json`, un `manifest.json` avec empreintes et hauteur
du sol, et les rapports JSON connus présents dans le dossier du run. Il exclut
la vidéo, les poids, le cache et l'environnement Python. Les métadonnées décrivent
ce que M1 a déclaré ; ce contrôle de cohérence ne prouve pas à lui seul une
exécution GPU. Les rapports déjà produits peuvent concerner l'ancienne version M2.

## Relecture et validation avant le commit

Avec Node >=22.18 et le checkout M3 préparé comme indiqué dans le guide :

```powershell
$m3Contract = 'D:\space_esb_m3\src\telemetry\contract.ts'
$manifest = Get-Content -Raw "$bundle/manifest.json" | ConvertFrom-Json
if ($manifest.frames -ne 30) { throw 'Le run final attendu contient 30 trames.' }
& $m1Python -m crater_m2.validation --output outputs/handoff-replay-01 --m3-contract $m3Contract -- --input "$bundle/observations.jsonl" --input-ground-z $manifest.groundZM --duration 10 --drain 60 --fps 10 --bandwidth 4096 --latency .005 --jitter 0 --loss .25 --blackout .5:2 --queue 128 --attempts 20
if ($LASTEXITCODE -ne 0) { throw 'La relecture M2/M3 a échoué.' }
$validation = Get-Content -Raw outputs/handoff-replay-01/validation.json | ConvertFrom-Json
if (-not $validation.canonicalM3Validated -or $validation.webSocketFrames -ne 30 -or $validation.m2Report.transport.acknowledged -ne 30) { throw 'Les 30 trames doivent être validées et acquittées.' }
```

Choisir un nouveau dossier de validation à chaque essai. Reprendre ensuite
le callback continu ONNX du guide avec `$scene/scene.mp4`, sa calibration et
le cache déjà préparé. Brancher enfin le véritable dashboard M3 et vérifier
les positions, la télémétrie périmée pendant la coupure et la récupération.
Le parser M3 seul ne valide pas l'affichage du dashboard.

## Commit et push du bundle

Après les contrôles précédents, publier seulement les petits artefacts. Le push
normal échoue si la branche distante a avancé ; aucun force-push n'est nécessaire.
Dans ce cas, conserver le commit, intégrer les changements distants et revalider.

```powershell
git add -- examples/m1-onnx-calibrated
git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw 'Corriger le diff avant le commit.' }
git diff --cached --stat
git commit -m "test(m1): publish calibrated ONNX handoff evidence"
if ($LASTEXITCODE -ne 0) { throw 'Échec du commit.' }
git push origin HEAD:feat/spatial-telemetry
if ($LASTEXITCODE -ne 0) { throw 'Push refusé : récupérer la branche distante et revalider.' }
```

Vérifier la CI du commit. La vidéo exacte peut être fournie séparément en pièce
jointe ou comme asset d'une Release GitHub, avec le SHA-256 de `manifest.video`.
Ne pas régénérer une vidéo en supposant qu'elle est identique : l'encodage peut
changer son empreinte. Publier son lien à côté du bundle une fois disponible.

La promotion vers `main` reste à effectuer après une validation commune M1/M2/M3
et une revue de l'intégration complète. Cette procédure ne modifie ni `main`
ni la branche M1 figée.
