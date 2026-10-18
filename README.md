# Japp — transcription locale, synthèse et présentation

> 🌐 **Site de téléchargement : https://alain-soumagne.github.io/Japp/**

Application Windows qui transforme un **enregistrement de cours** (audio ou vidéo) en :

1. une **transcription** complète (`.txt`, `.srt`, `.md` horodaté),
2. une **synthèse structurée** (notions, règles, exemples, devoirs),
3. une **présentation HTML** prête à projeter ou à réviser.

Tout se passe **sur ton ordinateur**, avec ta carte graphique NVIDIA : aucun compte, aucune API payante, aucun envoi de tes cours sur internet.
Pensée pour des cours de **japonais et de français** (y compris mélangés), elle fonctionne aussi pour d'autres langues gérées par Whisper.

```
Audio / vidéo ──► Whisper large-v3 (GPU) ──► transcription ──► LLM local via Ollama ──► synthèse ──► présentation HTML
```

---

## 1. Prérequis

| | Obligatoire | Détail |
|---|---|---|
| **Système** | Windows 10 ou 11, 64 bits | Seul Windows est supporté. |
| **Carte graphique** | NVIDIA (série RTX recommandée) | La transcription utilise CUDA. Sans GPU NVIDIA, l'application ne fonctionne pas. |
| **Pilote NVIDIA** | Récent | ≥ 570 pour les RTX 50xx ; mets-le à jour avec l'application NVIDIA si tu as un doute. Vérifie avec `nvidia-smi` dans un terminal. |
| **Mémoire vidéo (VRAM)** | **12 Go ou plus conseillé** | Whisper (≈ 5 Go) puis le modèle de synthèse (`gemma4:12b`, ≈ 9–10 Go) sont chargés **l'un après l'autre**. Avec 8–10 Go, choisis `gemma4:e4b` (plus léger, moins précis). |
| **Mémoire (RAM)** | 16 Go conseillés | |
| **Disque** | **≈ 20 Go libres** | Application et environnement Python ≈ 2,5 Go · modèle Whisper ≈ 3 Go · modèle de synthèse ≈ 8 Go · fichiers temporaires. |
| **Internet** | Au premier lancement et au premier usage de chaque modèle | Ensuite l'application fonctionne **hors ligne**. |
| **Ollama** | **Oui, pour la synthèse** | Gratuit — [ollama.com/download](https://ollama.com/download). Sans lui, la transcription marche mais pas la synthèse. |

> **Testé sur** : Windows 11, RTX 5080 (16 Go). Les autres cartes (RTX 3080 10 Go, etc.) ne sont pas encore validées : retours bienvenus.
> Tu n'as **rien d'autre à installer** : ni Python, ni ffmpeg, ni CUDA — l'application s'en occupe.

---

## 2. Installation (utilisateur)

### Étape 1 — Installer Ollama
Télécharge et installe [Ollama](https://ollama.com/download). Laisse les options par défaut. Il n'est pas nécessaire de le lancer : Japp le démarre quand il en a besoin.

### Étape 2 — Télécharger Japp
Va sur la page [**Releases**](../../releases/latest) du dépôt et télécharge **`Japp-Setup-x.y.z.exe`**.

*(Facultatif mais recommandé) Vérifie le fichier* — dans PowerShell, depuis le dossier de téléchargement :

```powershell
Get-FileHash .\Japp-Setup-*.exe -Algorithm SHA256    # compare avec SHA256SUMS.txt de la release
gh attestation verify .\Japp-Setup-*.exe --repo Alain-Soumagne/japp   # prouve que le fichier a été construit par GitHub Actions
```

### Étape 3 — Lancer l'installateur
Double-clique sur le fichier.

> ⚠️ **Windows SmartScreen** peut afficher « Windows a protégé votre ordinateur », car l'installateur n'est pas signé numériquement (un certificat de signature est payant).
> Clique sur **Informations complémentaires → Exécuter quand même**.

Choisis le dossier d'installation (ou garde celui par défaut), puis termine.

### Étape 4 — Premier démarrage (une seule fois)
Au premier lancement, Japp prépare son moteur : il télécharge Python et les bibliothèques de transcription (≈ 3 Go).
Une barre de progression s'affiche ; compte **5 à 15 minutes** selon ta connexion. **Ne ferme pas la fenêtre.**
Les démarrages suivants prennent quelques secondes.

### Étape 5 — Première synthèse
La première fois que tu traites un cours :
- le modèle Whisper (≈ 3 Go) est téléchargé automatiquement ;
- le modèle de synthèse (`gemma4:12b`, ≈ 8 Go) est téléchargé par Ollama.

Pour gagner du temps, tu peux le préparer à l'avance dans un terminal : `ollama pull gemma4:12b`.

---

## 3. Utilisation

1. Ouvre **Japp**.
2. **Glisse ton fichier** (ou plusieurs) dans la zone centrale, ou clique pour le choisir.
   Formats : mp3, m4a, wav, flac, ogg, opus, mp4, mkv, mov, webm, avi…
   **Ou colle un lien YouTube** (vidéo *publique* ou *non répertoriée*) dans le champ situé sous la zone de dépôt, puis clique sur *Importer* : Japp télécharge uniquement l'audio, le transcrit, puis le supprime. Les vidéos privées, réservées aux membres, les playlists et les chaînes ne sont pas encore prises en charge.
3. Avant de déposer, règle si besoin :
   - **Langue du cours** — *Français* si le cours est en français avec des mots japonais (ils seront écrits en romaji) ; *Japonais* si tout est en japonais ; *Automatique* sinon.
   - **Modèle de synthèse** — `gemma4:12b` par défaut.
   - **Vocabulaire** (optionnel) — noms propres, termes techniques : aide Whisper à les reconnaître.
4. Suis la progression : (téléchargement si lien YouTube →) transcription → modèle IA → synthèse → présentation. Une heure de cours demande quelques minutes sur une RTX récente (19 min d'audio ≈ 2 min sur RTX 5080).
5. Récupère le résultat dans les onglets :
   - **Présentation** — flèches ← → ou clic pour naviguer, `F` pour le plein écran, bouton « Ouvrir en grand ».
   - **Transcription** — corrige les erreurs, puis *Enregistrer et régénérer la synthèse* (sans retranscrire).
   - **Synthèse** — la version texte, avec le nombre d'exemples vérifiés.
   - Boutons de téléchargement : `.txt`, `.srt`, `.md`, `.json`, `.html`.

### Où sont mes données ?
Tout est dans `%LOCALAPPDATA%\Japp` (copie-colle ce chemin dans l'explorateur) :

| Élément | Emplacement |
|---|---|
| Tes cours traités | `data\jobs\<identifiant>\` |
| Environnement Python | `env\` |
| Journaux (en cas de problème) | `backend.log`, `setup.log` |
| Modèle Whisper | `%USERPROFILE%\.cache\huggingface` |
| Modèles de synthèse | `%USERPROFILE%\.ollama\models` |

Le bouton **Supprimer** efface un cours et tous ses fichiers.

### Désinstaller
*Paramètres Windows → Applications → Japp → Désinstaller.* Par prudence, tes données et l'environnement ne sont pas supprimés : efface ensuite le dossier `%LOCALAPPDATA%\Japp` pour récupérer l'espace. Les modèles (Whisper, Ollama) se suppriment séparément (dossiers ci-dessus ou `ollama rm gemma4:12b`).

---

## 4. Confidentialité

- Les enregistrements, transcriptions et synthèses **ne quittent jamais ta machine**. Pas de télémétrie, pas de compte.
- Si tu importes un **lien YouTube**, Japp contacte YouTube pour récupérer l'audio de cette vidéo (sans cookie ni compte). Respecte les conditions d'utilisation de YouTube et les droits d'auteur : n'importe que des vidéos dont tu as le droit de te servir.
- L'application ne se connecte à internet que pour **télécharger** : Python et ses bibliothèques (GitHub, PyPI), le modèle Whisper (Hugging Face), les modèles de synthèse (Ollama).
- Le moteur local n'écoute que sur `127.0.0.1` ; voir [SECURITY.md](SECURITY.md) pour le détail des protections.
- Les fichiers ne sont pas chiffrés : quiconque ouvre ta session Windows peut les lire.

---

## 5. Limites à connaître

- **Relis toujours le résultat.** Whisper peut mal entendre (noms propres, passages en japonais mêlés au français) et le modèle de synthèse peut se tromper.
- Les **exemples en japonais** ne sont retenus que s'ils figurent réellement dans la transcription (contrôle automatique) : il y en a donc peu. Les phrases lues à l'écran mais pas prononcées ne sont pas captées.
- La conversion romaji → kana est approximative (les noms propres en katakana sortent en hiragana).
- Une seule tâche à la fois (la carte graphique est partagée entre Whisper et le modèle de synthèse).
- Le modèle `gemma4:12b` plante sur certaines cartes RTX 50 avec *flash attention* : l'application le désactive automatiquement lorsqu'elle démarre Ollama elle-même. Si tu lances Ollama toi-même, définis `OLLAMA_FLASH_ATTENTION=0`.

---

## 6. Dépannage

| Symptôme | Cause probable | Solution |
|---|---|---|
| Bandeau « Aucun GPU NVIDIA détecté » | Pilote absent ou obsolète | Installe/mets à jour le pilote NVIDIA, redémarre, vérifie `nvidia-smi`. |
| Bandeau « Ollama n'est pas installé » | Ollama manquant | Installe-le depuis [ollama.com/download](https://ollama.com/download) (bouton dans l'application), relance Japp. |
| Le premier démarrage échoue ou reste bloqué | Connexion coupée, antivirus, disque plein | Vérifie internet et l'espace disque, relance Japp (les fichiers déjà téléchargés sont réutilisés), consulte `%LOCALAPPDATA%\Japp\setup.log`. |
| « Moteur arrêté » / fenêtre qui ne s'ouvre pas | Erreur du moteur local | Lis `%LOCALAPPDATA%\Japp\backend.log`. Pour repartir de zéro : ferme Japp, supprime `%LOCALAPPDATA%\Japp\env`, relance. |
| Erreur CUDA / mémoire insuffisante | VRAM trop juste | Ferme les jeux/applications GPU, ou choisis `gemma4:e4b`. |
| La synthèse échoue mais la transcription est bonne | Ollama ou modèle indisponible | Ouvre l'onglet *Transcription* puis *Enregistrer et régénérer*, ou vérifie `ollama list`. |
| Transcription vide ou absurde | Mauvaise langue, audio très bruité | Force la langue (*Français* / *Japonais*), ajoute du vocabulaire, vérifie l'audio. |
| SmartScreen bloque l'installateur | Installateur non signé | *Informations complémentaires → Exécuter quand même* après avoir vérifié la somme SHA-256. |

Un autre problème ? Ouvre un ticket en joignant `backend.log` (**relis-le avant : il peut contenir des noms de fichiers**) et la version indiquée dans le nom de l'installateur.

---

## 7. Développement

**Pile** : backend Python (FastAPI) · interface Angular · fenêtre Electron · transcription faster-whisper · synthèse Ollama.

```
backend/     API locale : transcription, synthèse, génération de la présentation, file de tâches
frontend/    interface Angular (servie par le backend)
electron/    fenêtre de bureau, création de l'environnement Python au 1er lancement, packaging
scripts/     contrôle des données sensibles
.github/     intégration continue, publication automatique, analyse de sécurité
```

**Prérequis développeur** : Windows, GPU NVIDIA, [Node.js](https://nodejs.org) `^22.22.3` ou `^24.15`, [uv](https://docs.astral.sh/uv/), [Ollama](https://ollama.com/download).

```powershell
git clone https://github.com/Alain-Soumagne/japp.git
cd japp

# Python 3.12 + dépendances (versions épinglées)
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -r requirements.txt -r requirements-dev.txt

# Tests et lint du backend
cd backend; ..\.venv\Scripts\python.exe -m ruff check .; ..\.venv\Scripts\python.exe -m pytest; cd ..

# Interface
cd frontend; npm ci; npm run build; cd ..

# Lancer l'application en mode développement
cd electron; npm ci; npm start
```

Construire l'installateur en local : `cd electron; npm run dist` → `electron/dist/Japp-Setup-<version>.exe`.
Avant tout *commit* public : `python scripts/check-sensitive.py`.

Publier une version : voir [docs/RELEASING.md](docs/RELEASING.md).

---

## 8. Licences et remerciements

Code : [MIT](LICENSE).
S'appuie sur [faster-whisper](https://github.com/SYSTRAN/faster-whisper) / [Whisper](https://github.com/openai/whisper) (MIT), [Ollama](https://ollama.com) (MIT), [FastAPI](https://fastapi.tiangolo.com) (MIT), [Angular](https://angular.dev) (MIT), [Electron](https://www.electronjs.org) (MIT), [uv](https://github.com/astral-sh/uv) (MIT/Apache-2.0).

Les **modèles** ne sont pas distribués avec l'application : chacun est téléchargé par l'utilisateur sous sa propre licence (Whisper : MIT · Gemma : [conditions d'utilisation de Google](https://ai.google.dev/gemma/terms) · Qwen3 : Apache-2.0).
Les bibliothèques NVIDIA CUDA (cuBLAS, cuDNN) sont téléchargées depuis PyPI sur la machine de l'utilisateur, sous licence NVIDIA.
