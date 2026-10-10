# NAIF/JPL — SPICE et repères de coordonnées
Source URL: https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/frames.html
Verified on: 2026-10-10

Résumé de Reference Frames, révision du 31 décembre 2021. SPICE décrit les relations entre repères. pxform transforme des vecteurs de position par rotation ; sxform transforme des états position/vitesse. De nombreux changements de repères exigent des kernels PCK, CK, FK ou SPK appropriés, chargés pour l'époque étudiée.

Application C.R.A.T.E.R. : nommer un repère ne fournit pas une pose. Une rotation ne change pas à elle seule l'origine d'une position. M1/M2/M3 doivent partager origine, axes, unités et instant ; une transformation vers LOCAL_ENU_V1 doit être explicite. SPICE n'est pas intégré ici et aucune pose n'est déduite automatiquement des vidéos NASA.
