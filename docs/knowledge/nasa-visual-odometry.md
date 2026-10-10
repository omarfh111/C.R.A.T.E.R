# JPL — odométrie visuelle et glissement des roues
Source URL: https://robotics.jpl.nasa.gov/what-we-do/flight-projects/mars-science-laboratory/surface-system-software-and-rover-navigation/
Verified on: 2026-10-10

Résumé de JPL Robotics sur Curiosity, page sans date de publication affichée. Le rover combine gyroscopes, accéléromètres et rotations des roues pour suivre sa pose. L'odométrie visuelle compare des images avant/après un déplacement, suit des caractéristiques du terrain et estime une pose à six degrés de liberté. Elle aide à détecter le glissement des roues.

Limite C.R.A.T.E.R. : compter des rotations ne prouve pas le déplacement réel. Suivre les identifiants des rochers n'est pas estimer la pose de la caméra. M2 utilise la pose calibrée fournie par M1 ; ce document n'ajoute ni odométrie visuelle ni fusion inertielle au logiciel.
