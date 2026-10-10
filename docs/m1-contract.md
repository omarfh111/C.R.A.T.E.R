# M1 -> M2 : observations visuelles v1

M1 fournit un objet JSON par image traitee dans un fichier JSONL. Ce format
est une proposition d'adaptateur M1, pas le JSON canonique spatial M2 -> M3.

- `schemaVersion`: 1, `roverId`: chaine, `sequence`: entier croissant.
- `capturedAt`: UTC ISO 8601 de traitement/relecture, pas la date historique NASA.
- `source`: nom du fichier, `frame_index`, `video_time_s`, `capture_timing`: "video_playback_unknown_original_cadence".
- `image`: `width`, `height`, `crop_xywh` dans la video originale.
- `camera`: null si non calibree ; sinon resolution, fx/fy/cx/cy,
  center_enu_m, rotation_camera_to_enu. Pixels exprimes dans l'image recadree.
- `rover_position_enu_m`: null si inconnue.
- `detections`: id stable dans la session, type, bbox_px [x1,y1,x2,y2],
  contact_pixel_px [u,v], confidence [0,1], observedAt UTC.

Le point de contact est le milieu bas de la boite : estimation approximative
sur un plan de sol, pas une mesure de profondeur. M2 doit refuser une
localisation metrique sans camera/pose calibrees. Pour une camera mobile,
une pose par image est requise. Le recadrage change cx/cy ; ne pas reutiliser
les parametres de l'image complete. Aucun pixel NASA ne recoit de metres inventes.

Le score du detecteur n'est pas une probabilite calibree. Les observations
ne contiennent que les detections du frame actuel ; les pistes temporairement
perdues sont gardees en memoire pour association mais jamais retransmises
comme observations fraiches. M2 calcule x/y/z et l'incertitude spatiale.
