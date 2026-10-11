# Calibration de la confiance des réseaux neuronaux
Source URL: https://arxiv.org/abs/1706.04599v2
Verified on: 2026-10-10

Résumé de l'abstract de Guo, Pleiss, Sun et Weinberger, ICML 2017, v2 du 3 août 2017. La calibration cherche à rapprocher les probabilités prédites de la fréquence réelle de réponses correctes. Les expériences de classification montrent que des réseaux modernes peuvent être mal calibrés ; les auteurs étudient notamment le temperature scaling.

Application C.R.A.T.E.R. : un score de détection de 0,9 ne prouve pas 90 % de réussite sans évaluation annotée adaptée. Cette étude de classification ne calibre pas directement Grounding DINO. La confiance d'une classe et l'incertitude de position en mètres sont différentes. La calibration statistique du score ne remplace pas la calibration géométrique de la caméra.
