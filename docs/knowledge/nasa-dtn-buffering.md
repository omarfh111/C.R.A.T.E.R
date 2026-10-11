# NASA — communications interrompues et stockage
Source URL: https://www.nasa.gov/reference/delay-disruption-tolerant-networking-overview/
Verified on: 2026-10-10

Résumé de l'aperçu NASA DTN, page évolutive sans date de publication retenue. Delay/Disruption Tolerant Networking traite les déconnexions, délais et débits différents entre liens. Son architecture stocke les bundles lorsque le prochain relais est indisponible, puis les transmet quand un contact devient possible. Un chemin complet disponible au même instant n'est pas nécessaire.

Limite C.R.A.T.E.R. : M2 possède son propre protocole binaire, buffer et retransmissions ; ce n'est pas une implémentation du Bundle Protocol NASA. La récupération dépend du retour du lien, des limites de file et d'abandon. Vérifier pending, queueDropped, abandoned, pertes et délais ; une coupure trop longue peut empêcher une livraison complète.
