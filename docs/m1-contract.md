# M1 -> M2 : observations visuelles v1

M1 fournit un objet JSON par image traitee dans un fichier JSONL. Ce format
respecte les champs requis de M2 pour les observations calibrees, et ajoute
des metadonnees pixels. Il reste distinct du JSON spatial M2 -> M3.

- `schemaVersion`: 1, `roverId`: chaine, `sequence`: entier croissant.
- `capturedAt`: UTC ISO 8601 de traitement/relecture, pas la date historique NASA.
- `source`: nom du fichier, `frame_index`, `video_time_s`, `capture_timing`: "video_playback_unknown_original_cadence".
- `image`: `width`, `height`, `crop_xywh` dans la video originale.
- `camera`: null si non calibree ; sinon resolution, fx/fy/cx/cy,
  centerEnuM, rotationCameraToEnu. Pixels exprimes dans l'image recadree.
- `roverPosition`: null si inconnue ; sinon {frameId:"LOCAL_ENU_V1", xM,yM,zM}.
- `positionUncertaintyRadiusM`: null si non calibree ; budget fourni par le scenario sinon.
- `detections`: id stable dans la session, type, bboxPx [x1,y1,x2,y2],
  contactPixel [u,v], confidence [0,1], observedAt UTC.

Le point de contact est le milieu bas de la boite : estimation approximative
sur un plan de sol, pas une mesure de profondeur. M2 doit refuser une
localisation metrique sans camera/pose calibrees. Pour une camera mobile,
une pose par image est requise. Le recadrage change cx/cy ; ne pas reutiliser
les parametres de l'image complete. Aucun pixel NASA ne recoit de metres inventes.

Le score du detecteur n'est pas une probabilite calibree. Les observations
ne contiennent que les detections du frame actuel ; les pistes temporairement
perdues sont gardees en memoire pour association mais jamais retransmises
comme observations fraiches. M2 calcule x/y/z et l'incertitude spatiale.

Les observations calibrees respectent directement le contrat publie par M2 :
`docs/m1-observation-contract.md` sur `feat/spatial-telemetry`.
Les champs source/image/sequence sont des metadonnees M1 supplementaires,
ignorees par M2. Un fichier NASA sans calibration n'est pas une entree metrique
acceptable pour M2 et doit rester reserve aux tests de perception.
