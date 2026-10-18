# Politique de sécurité

## Signaler une vulnérabilité

Merci de **ne pas ouvrir de ticket public** pour un problème de sécurité.
Utilise plutôt l'onglet **Security → Report a vulnerability** (signalement privé GitHub) de ce dépôt.
Indique les étapes pour reproduire, la version concernée et l'impact estimé. Une réponse est donnée dès que possible.

Seule la dernière version publiée reçoit des correctifs de sécurité.

## Modèle de menace

Japp est une application **locale** : elle ne comporte ni compte, ni serveur distant, ni télémétrie.
Les enregistrements, transcriptions, synthèses et présentations restent sur la machine de l'utilisateur.

| Surface | Mesure |
|---|---|
| API locale (FastAPI) | N'écoute que sur `127.0.0.1` (port aléatoire choisi au lancement). Pas de CORS, documentation interactive désactivée. |
| Page web malveillante visant l'API | Contrôle de l'en-tête `Host` (anti *DNS rebinding*) et de l'en-tête `Origin` sur toute requête qui modifie l'état (anti-CSRF). |
| Fichiers servis | Liste blanche stricte de 5 noms de fichiers par tâche ; identifiants de tâche validés ; aucun accès à un chemin arbitraire. |
| Liens YouTube | Seuls `youtube.com` et `youtu.be` en `https` sont acceptés ; l'identifiant de vidéo (11 caractères) est extrait puis l'URL est reconstruite. Pas de playlist, pas de cookie, pas de fichier de configuration, pas de programme externe lancé. Audio seul, durée et taille plafonnées, supprimé après transcription. |
| Exercices | Identifiants de session validés (alphanumériques), réponses et arguments de contestation bornés en taille et transmis au modèle comme données encadrées (jamais comme instructions), le corrigé n'est pas envoyé à l'interface avant l'envoi des réponses. Un score truqué n'affecte que le profil local de l'utilisateur. |
| Fichiers envoyés / ouverts | Extensions audio/vidéo uniquement, taille limitée, noms générés (jamais celui fourni par le client). |
| Interface (Electron) | `contextIsolation`, `sandbox`, pas de `nodeIntegration`, navigation hors application bloquée, permissions web refusées, ouverture externe limitée à une liste blanche (`ollama.com`, `github.com`). |
| Interface web | Content-Security-Policy stricte (`script-src 'self'`). Les présentations générées s'ouvrent dans une `iframe` en bac à sable (`sandbox="allow-scripts"`) avec une CSP sans accès réseau ; le contenu issu du modèle de langage est toujours inséré en texte (jamais en HTML). |
| Chaîne d'approvisionnement | Dépendances Python **épinglées**, `uv` téléchargé avec **empreinte SHA-256 vérifiée**, GitHub Actions épinglées par SHA de commit, Dependabot, CodeQL, `npm audit` / `pip-audit` en CI. |
| Publication | Release construite par GitHub Actions uniquement ; somme SHA-256 et **attestation de provenance** fournies. |

### Limites connues
- L'installateur Windows n'est pas signé numériquement (certificat payant) : SmartScreen peut afficher un avertissement. Vérifie la somme SHA-256 et l'attestation (voir le README).
- Les modèles (Whisper, Gemma, Qwen…) sont téléchargés depuis Hugging Face / Ollama au premier usage ; leur intégrité repose sur ces services.
- Les dépendances de **build** d'`electron-builder` signalent des alertes de gravité modérée (`npm audit`) : elles n'existent qu'au moment de la construction et ne sont pas livrées dans l'application.
- Quiconque peut exécuter du code sur ta session Windows peut lire tes données (dossier `%LOCALAPPDATA%\Japp`) : elles ne sont pas chiffrées.
