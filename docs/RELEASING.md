# Publier une version

La publication est **entièrement automatique** : pousser un tag `vX.Y.Z` déclenche
[`release.yml`](../.github/workflows/release.yml), qui construit l'installateur Windows sur GitHub,
calcule sa somme SHA-256, génère une attestation de provenance et crée la *release* avec les fichiers.

## Procédure

```powershell
# 1. Tout est propre et testé
python scripts/check-sensitive.py
cd backend; ..\.venv\Scripts\python.exe -m pytest; cd ..

# 2. Passer la version (electron/package.json) — le tag DOIT correspondre
cd electron; npm version 0.2.0 --no-git-tag-version; cd ..
git add electron/package.json electron/package-lock.json
git commit -m "Version 0.2.0"

# 3. Tag + push : lance la publication
git tag v0.2.0
git push origin main v0.2.0
```

Suis l'avancement dans l'onglet **Actions**. En ~10 minutes, la page **Releases** contient :
`Cours-Setup-0.2.0.exe` et `SHA256SUMS.txt`, avec les notes générées automatiquement.
Un tag contenant un tiret (`v0.2.0-beta.1`) crée une *pré-version*.

Le workflow échoue volontairement si : le tag ne correspond pas à `electron/package.json`,
`scripts/check-sensitive.py` trouve une donnée sensible, ou l'empreinte de `uv` ne correspond pas.

## Première publication du dépôt — liste de contrôle

- [ ] `python scripts/check-sensitive.py` → « Aucune donnée sensible détectée ».
- [ ] `git status` : aucun dossier `data/`, `.venv/`, `node_modules/`, `dist/`, aucun fichier audio/vidéo/`.log`.
- [ ] **Identité Git** : utilise l'adresse *noreply* de GitHub pour ne pas exposer ton e-mail dans l'historique :
      `git config user.name "ton-pseudo"` et `git config user.email "ID+ton-pseudo@users.noreply.github.com"`
      (GitHub → Settings → Emails → « Keep my email addresses private »). Un ID numérique s'obtient avec `https://api.github.com/users/<pseudo>`.
- [ ] Le `README.md` pointe vers le dépôt `Alain-Soumagne/transcribe` (à adapter si le dépôt est renommé).
- [ ] Dans **Settings → Code security** du dépôt, active : *Dependabot alerts*, *Dependabot security updates*,
      *Secret scanning* + *Push protection*, *Private vulnerability reporting*.
- [ ] Dans **Settings → Actions → General** : *Workflow permissions* = « Read repository contents » (les workflows
      demandent eux-mêmes `contents: write` uniquement pour l'étape de publication).
- [ ] **Settings → Branches** : protège `main` (PR obligatoire, CI verte) ; **Settings → Tags** : règle de protection sur `v*`.
- [ ] Vérifie que `LICENSE` porte bien le nom du titulaire des droits que tu souhaites.

## Signature de code (facultatif)

L'installateur n'est pas signé : SmartScreen avertit les nouveaux utilisateurs. Pour signer :

1. Obtiens un certificat de signature de code (`.pfx`) auprès d'une autorité reconnue.
2. Ajoute les secrets `CSC_LINK` (certificat encodé en base64) et `CSC_KEY_PASSWORD` dans **Settings → Secrets → Actions**.
3. Dans `release.yml`, retire `CSC_IDENTITY_AUTO_DISCOVERY: 'false'` et transmets les deux secrets à l'étape *Construire l'installateur*.

## Mises à jour des dépendances

- **Actions GitHub** : épinglées par SHA de commit (commentaire `# vN`). Dependabot propose les mises à jour chaque semaine.
- **Python** : `requirements.in` (dépendances directes) → `uv pip compile requirements.in -o requirements.txt` (versions épinglées). Teste ensuite sur une machine avec GPU.
- **uv embarqué** : modifie `UV_VERSION` et `UV_SHA256` dans `electron/scripts/fetch-uv.mjs`
  (l'empreinte est publiée à côté de l'archive : `…/releases/download/<version>/uv-x86_64-pc-windows-msvc.zip.sha256`).
- **npm** : Dependabot ; relance `npm run build` et `npm test`.

## Que contient l'installateur ?

Environ 110 Mo : Electron, l'interface, le backend Python (code source), `requirements.txt` et `uv.exe`.
L'environnement Python (≈ 2,5 Go, dont les bibliothèques CUDA) n'est **pas** embarqué : il est créé au premier lancement
dans `%LOCALAPPDATA%\Cours\env` (voir `electron/bootstrap.js`). Cela évite de dépasser la limite de 2 Go d'une release GitHub
et de redistribuer les bibliothèques NVIDIA.
