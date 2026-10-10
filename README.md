# C.R.A.T.E.R. - M1

Branche `feat/ai-perception` : perception locale, tracking et observations
pixels pour M2. La localisation et le transport restent dans `crater_m2`.

Installation (Python 3.11+, environnement virtuel conseille) :

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[test]"
.\.venv\Scripts\python -m pytest
```

Voir `docs/m1-contract.md` pour les conventions d'echange. Le modele et
l'executable de demo seront ajoutes dans le prochain lot valide.
