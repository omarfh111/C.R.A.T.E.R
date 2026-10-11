# Journal d'expérience et diagnostic local — 11 octobre 2026

L'utilisateur autorise l'implémentation autonome du journal et de l'analyse,
avec préparation multimodale sans imposer un nouveau modèle ou modifier M1/M3.

Architecture : SQLite local pour événements, travaux d'analyse et relectures.
HTTP loopback pour M3 ; un seul worker LLM et une file bornée. Les événements
peuvent inclure une trame canonique v1 et des références d'images vérifiées,
mais les pixels ne sont jamais envoyés au modèle textuel. Les décisions réelles
et les explications du modèle sont enregistrées séparément.

- [x] Journal et validation : types d'incidents explicites, provenance déclarée
  réelle/simulée/opérateur, UUID idempotent, horodatages, décision facultative,
  trame validée par M2, images relatives à une racine choisie par l'opérateur.
  Tests : persistance, conflits, entrées invalides, intégrité des images.
- [x] Diagnostic : contexte événement immuable et cité, questions par type,
  file persistante bornée, résultats/erreurs, reprise après interruption,
  modèle sérialisé sans bloquer ingestion ou polling. Tests avec modèle double
  explicitement déclaré, worker lent et défaillant.
- [x] HTTP/CLI/client M3 : endpoints événements/travaux, option `--journal`,
  relecture et export manuels, client TypeScript et contrat documentés.
  Tests HTTP réels, TypeScript strict et compatibilité `/ask` existante.
- [x] Vérification finale : suite complète, essai local Ollama sur un événement
  explicitement simulé, relecture, commits atomiques Conventional Commit et
  push de chacun sur `feat/spatial-telemetry`, CI verte.

Bornes : événement JSON <= 32 KiB ; journal <= 10 000 événements ; file <= 16
travaux non terminés ; images <= 4 références et 5 MiB chacune. La file pleine
refuse l'analyse explicitement. Pas de commande moteur, réentraînement,
promotion automatique au corpus ni revendication de raisonnement interne du robot.

Validation locale : 285 tests Python réussis (3 ignorés), 9 tests du client
réussis, compilation TypeScript stricte et relecture indépendante sans P1/P2
restant. Essai Ollama réel : acceptation 38,6 ms, résultat reçu en 104,1 s.
Voir [le rapport](validation/experience-local.md). Les deux jobs Python de la
CI du commit `b751c26` ont réussi.
