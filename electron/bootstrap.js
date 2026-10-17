// Création de l'environnement Python au premier lancement (version installée) :
//   uv venv --python 3.12  +  uv pip install -r requirements.txt  (Whisper, CUDA, FastAPI…, ~3 Go)
// Idempotent : un marqueur contient l'empreinte de requirements.txt ; l'environnement n'est recréé que si elle change.
const { spawn } = require('node:child_process');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const PYTHON_VERSION = '3.12';

function sha256(file) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

function pythonPath(envDir) {
  return path.join(envDir, 'Scripts', 'python.exe');
}

function isReady(envDir, requirementsPath) {
  try {
    const marker = JSON.parse(fs.readFileSync(path.join(envDir, '.cours-env.json'), 'utf8'));
    return marker.requirements === sha256(requirementsPath) && fs.existsSync(pythonPath(envDir));
  } catch {
    return false;
  }
}

function run(cmd, args, { env, onLine, cwd }) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { env, cwd, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
    const tail = [];
    const feed = (buf) => {
      for (const line of buf.toString('utf8').split(/\r?\n/)) {
        if (!line.trim()) continue;
        tail.push(line);
        if (tail.length > 40) tail.shift();
        onLine?.(line);
      }
    };
    child.stdout.on('data', feed);
    child.stderr.on('data', feed);
    child.on('error', reject);
    child.on('exit', (code) =>
      code === 0 ? resolve() : reject(new Error(`${path.basename(cmd)} a échoué (code ${code}).\n${tail.slice(-12).join('\n')}`)));
  });
}

/**
 * @param {{uvPath:string, requirementsPath:string, envDir:string, cacheDir:string,
 *          onStatus:(text:string, pct:number|null)=>void, onLog?:(line:string)=>void}} o
 * @returns {Promise<string>} chemin de python.exe
 */
async function ensureEnv({ uvPath, requirementsPath, envDir, cacheDir, onStatus, onLog }) {
  if (isReady(envDir, requirementsPath)) return pythonPath(envDir);
  if (!fs.existsSync(uvPath)) throw new Error(`uv introuvable : ${uvPath}`);

  const env = {
    ...process.env,
    UV_CACHE_DIR: cacheDir,
    UV_LINK_MODE: 'copy',            // pas de liens physiques entre disques
    UV_NO_PROGRESS: '1',
    UV_PYTHON_PREFERENCE: 'only-managed',
    PYTHONUTF8: '1',
  };
  fs.mkdirSync(path.dirname(envDir), { recursive: true });
  fs.rmSync(envDir, { recursive: true, force: true });

  const n = fs.readFileSync(requirementsPath, 'utf8').split(/\r?\n/).filter((l) => l.trim() && !l.startsWith('#')).length;
  let seen = 0;
  const log = (l) => onLog?.(l);

  onStatus(`Installation de Python ${PYTHON_VERSION}…`, 2);
  await run(uvPath, ['venv', envDir, '--python', PYTHON_VERSION], { env, onLine: log });

  onStatus('Téléchargement des bibliothèques (Whisper, CUDA…) — environ 3 Go, patiente quelques minutes.', 8);
  await run(uvPath, ['pip', 'install', '--python', pythonPath(envDir), '-r', requirementsPath], {
    env,
    onLine: (l) => {
      log(l);
      // uv écrit « + paquet==version » à chaque paquet installé : sert d'indicateur de progression
      if (/^\s*\+\s/.test(l)) seen++;
      const m = l.match(/^\s*(Downloading|Downloaded|Prepared|Installed)\s+(.*)/);
      onStatus(m ? `${m[1] === 'Downloading' ? 'Téléchargement' : 'Installation'} : ${m[2].slice(0, 60)}` : 'Installation des bibliothèques…',
               Math.min(98, 10 + Math.round((seen / Math.max(n, 1)) * 85)));
    },
  });

  fs.writeFileSync(path.join(envDir, '.cours-env.json'),
    JSON.stringify({ requirements: sha256(requirementsPath), python: PYTHON_VERSION, created: new Date().toISOString() }));
  fs.rmSync(cacheDir, { recursive: true, force: true });   // libère ~3 Go de cache de téléchargement
  onStatus('Environnement prêt.', 100);
  return pythonPath(envDir);
}

module.exports = { ensureEnv, isReady, pythonPath };
