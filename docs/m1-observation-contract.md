# Entrée M1 -> M2 : observations calibrées JSONL

Une ligne JSON = un groupe de détections d'une image. M2 peut aussi appeler
`observation_to_frame(observation, sequence, link)` directement depuis Python.
La caméra est déjà rectifiée ; aucune API cloud nécessaire.

Champs obligatoires de l'observation :

| Champ | Sens |
|---|---|
| roverId | identifiant non vide du rover, constant dans un flux |
| capturedAt | capture ISO 8601 avec timezone |
| roverPosition | `{frameId:"LOCAL_ENU_V1", xM, yM, zM}`, mètres |
| positionUncertaintyRadiusM | budget spatial de pose >=0, mètres |
| camera | calibration et pose décrites ci-dessous |
| detections | liste éventuellement vide |

`camera` : `width`, `height` (pixels entiers positifs), `fx`, `fy`, `cx`, `cy`
(pixels), `centerEnuM` (3 nombres en mètres), `rotationCameraToEnu` (matrice 3x3,
orthonormale directe). Axes caméra : x à droite, y vers le bas, z vers l'avant.
La matrice transforme un vecteur caméra en vecteur ENU. Centre et rotation sont
ceux de la capture, pas une pose fixe si le rover se déplace.

Options de l'observation : `groundZM` (hauteur du plan, défaut 0), `maxRangeM`
(portée depuis la caméra, défaut 1000 m).

Chaque détection :

- `id` stable pour le même danger ; ne pas réinitialiser à chaque image.
- `type` : `rock`, `crater`, `slope` ou `unknown`.
- `confidence` entre 0 et 1, indépendante de l'incertitude spatiale.
- `contactPixel: [u,v]` **ou** `bboxPx: [x1,y1,x2,y2]` ; contact prioritaire
  s'il est fourni. Sinon M2 utilise le milieu du bord inférieur de la boîte.
- `observedAt` optionnel, défaut capture ; jamais après `capturedAt`.
- `pixelErrorPx` optionnel, défaut 2 ; amplitude de perturbation par axe.

Les boîtes doivent avoir une surface positive et un contact inférieur visible.
Un contact au sol n'est pas approprié à tous les dangers : pour un cratère,
fournir par exemple un pixel de bord identifié, sans prétendre mesurer sa profondeur.
M2 ne déduit pas une calibration à partir du seul nom de caméra ou du MP4.

M2 attribue les séquences aux trames générées et les compteurs de liaison à la
capture. Il produit uniquement les champs du contrat M3, jamais la calibration,
les pixels ou la vérité terrain dans la télémétrie canonique.

Voir `examples/m1-observations.jsonl` pour trois observations utilisables.
