// Notification de nouvelle version + téléchargement VÉRIFIÉ de l'installateur (l'installation reste à la main de l'utilisateur).
//
// Sécurité :
//  - une seule URL d'interrogation fixe (API GitHub du dépôt), exécutée par le processus principal, jamais par la page ;
//  - la release n'est acceptée que si son étiquette est de la forme vX.Y.Z et si les fichiers pointent vers github.com/<dépôt>/ ;
//  - redirections suivies uniquement vers GitHub (liste blanche d'hôtes), en https ;
//  - l'installateur n'est conservé que si son SHA-256 correspond à SHA256SUMS.txt publié dans la même release ;
//  - rien n'est lancé automatiquement.
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const https = require('node:https');
const path = require('node:path');

const MAX_EXE_BYTES = 600 * 1024 * 1024;
const MAX_TEXT_BYTES = 256 * 1024;
const TIMEOUT_MS = 15_000;
const HOSTS = [/^api\.github\.com$/, /^github\.com$/, /(^|\.)githubusercontent\.com$/];

function parseVersion(v) {
  const m = /^v?(\d+)\.(\d+)\.(\d+)$/.exec(String(v || '').trim());
  return m ? [Number(m[1]), Number(m[2]), Number(m[3])] : null;
}

/** >0 si a > b, <0 si a < b, 0 si égales ; null si l'une n'est pas une version valide X.Y.Z. */
function compareVersions(a, b) {
  const x = parseVersion(a), y = parseVersion(b);
  if (!x || !y) return null;
  for (let i = 0; i < 3; i++) if (x[i] !== y[i]) return x[i] - y[i];
  return 0;
}

const isAllowedHost = (url) => {
  try { const u = new URL(url); return u.protocol === 'https:' && HOSTS.some((r) => r.test(u.hostname)); } catch { return false; }
};

/** Transforme la réponse de l'API GitHub en informations de mise à jour, ou null si la release n'est pas acceptable. */
function parseRelease(json, repo) {
  if (!json || json.draft || json.prerelease || typeof json.tag_name !== 'string') return null;
  const version = parseVersion(json.tag_name) && json.tag_name.replace(/^v/, '');
  if (!version || !/^v\d+\.\d+\.\d+$/.test(json.tag_name)) return null;
  const prefix = `https://github.com/${repo}/releases/download/`;
  const assets = Array.isArray(json.assets) ? json.assets : [];
  const exe = assets.find((a) => /^Japp-Setup-\d+\.\d+\.\d+\.exe$/.test(a.name) && a.browser_download_url?.startsWith(prefix));
  const sums = assets.find((a) => a.name === 'SHA256SUMS.txt' && a.browser_download_url?.startsWith(prefix));
  if (!exe || !sums || exe.name !== `Japp-Setup-${version}.exe`) return null;
  const htmlUrl = `https://github.com/${repo}/releases/tag/${json.tag_name}`;
  return {
    version,
    notes: String(json.body || '').replace(/\r/g, '').slice(0, 2500),
    exe: { name: exe.name, url: exe.browser_download_url, size: Number(exe.size) || 0 },
    sumsUrl: sums.browser_download_url,
    htmlUrl,
  };
}

/** Trouve le SHA-256 attendu pour `name` dans un fichier au format `sha256sum` ("<hash>  <fichier>"). */
function expectedHash(text, name) {
  for (const line of String(text).split(/\r?\n/)) {
    const m = /^([0-9a-fA-F]{64})\s+\*?(.+?)\s*$/.exec(line);
    if (m && path.basename(m[2].replace(/\\/g, '/')) === name) return m[1].toLowerCase();
  }
  return null;
}

/** GET avec redirections contrôlées. `deps.allow(url)` remplace la liste blanche (tests). */
function get(url, deps = {}, headers = {}, redirects = 5) {
  const allow = deps.allow || isAllowedHost;
  return new Promise((resolve, reject) => {
    if (!allow(url)) return reject(new Error('Adresse non autorisée'));
    const lib = url.startsWith('http://') ? http : https;
    const req = lib.get(url, { headers: { 'User-Agent': 'Japp-updater', ...headers }, timeout: TIMEOUT_MS }, (res) => {
      if ([301, 302, 303, 307, 308].includes(res.statusCode) && res.headers.location) {
        res.resume();
        if (redirects <= 0) return reject(new Error('Trop de redirections'));
        return resolve(get(new URL(res.headers.location, url).href, deps, headers, redirects - 1));
      }
      if (res.statusCode !== 200) { res.resume(); return reject(new Error(`HTTP ${res.statusCode}`)); }
      resolve(res);
    });
    req.on('timeout', () => req.destroy(new Error('Délai dépassé')));
    req.on('error', reject);
  });
}

async function readText(url, deps, limit = MAX_TEXT_BYTES) {
  const res = await get(url, deps);
  let size = 0;
  const chunks = [];
  for await (const c of res) {
    size += c.length;
    if (size > limit) { res.destroy(); throw new Error('Réponse trop volumineuse'); }
    chunks.push(c);
  }
  return Buffer.concat(chunks).toString('utf8');
}

/** Interroge GitHub. Retourne { latest: info|null, newer: bool }. */
async function checkLatest({ repo, current, deps = {} }) {
  const api = deps.apiUrl || `https://api.github.com/repos/${repo}/releases/latest`;
  const json = JSON.parse(await readText(api, deps, 512 * 1024));
  const info = parseRelease(json, repo);
  const cmp = info ? compareVersions(info.version, current) : null;
  return { latest: info, newer: cmp !== null && cmp > 0 };
}

/** Télécharge l'installateur dans `destDir` et ne le conserve que si son SHA-256 est celui publié. Retourne le chemin final. */
async function downloadVerified({ info, destDir, onProgress = () => {}, deps = {} }) {
  const expected = expectedHash(await readText(info.sumsUrl, deps), info.exe.name);
  if (!expected) throw new Error("Somme SHA-256 introuvable dans la release : téléchargement annulé.");
  fs.mkdirSync(destDir, { recursive: true });
  const final = path.join(destDir, info.exe.name);
  const part = `${final}.part`;
  const res = await get(info.exe.url, deps);
  const total = Number(res.headers['content-length']) || info.exe.size || 0;
  if (total > MAX_EXE_BYTES) { res.destroy(); throw new Error('Fichier anormalement volumineux.'); }
  const hash = crypto.createHash('sha256');
  const out = fs.createWriteStream(part);
  let done = 0;
  try {
    await new Promise((resolve, reject) => {
      res.on('data', (c) => {
        done += c.length;
        if (done > MAX_EXE_BYTES) return res.destroy(new Error('Fichier anormalement volumineux.'));
        hash.update(c);
        out.write(c);
        if (total) onProgress(done / total);
      });
      res.on('end', () => out.end(resolve));
      res.on('error', reject);
      res.on('aborted', () => reject(new Error('Téléchargement interrompu.')));
      out.on('error', reject);
    });
    if (hash.digest('hex') !== expected) throw new Error("Le fichier téléchargé ne correspond pas à la somme SHA-256 publiée : il a été supprimé.");
    fs.rmSync(final, { force: true });
    fs.renameSync(part, final);
  } catch (e) {
    out.destroy();
    fs.rmSync(part, { force: true });
    throw e;
  }
  return final;
}

// --- préférences (%LOCALAPPDATA%\Japp\updates.json) ---
function loadPrefs(file) {
  try {
    const p = JSON.parse(fs.readFileSync(file, 'utf8'));
    return { enabled: p.enabled !== false, lastCheck: Number(p.lastCheck) || 0, skipped: typeof p.skipped === 'string' ? p.skipped : '' };
  } catch { return { enabled: true, lastCheck: 0, skipped: '' }; }
}
function savePrefs(file, prefs) {
  try { fs.writeFileSync(file, JSON.stringify(prefs)); } catch { /* disque en lecture seule : sans conséquence */ }
}

module.exports = { compareVersions, parseVersion, parseRelease, expectedHash, checkLatest, downloadVerified, loadPrefs, savePrefs, isAllowedHost };
