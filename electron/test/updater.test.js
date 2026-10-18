// Tests du module de mise à jour : comparaison de versions, lecture stricte de la release, téléchargement vérifié (faux serveur local).
const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const u = require('../updater');

const REPO = 'Alain-Soumagne/Japp';
const DL = `https://github.com/${REPO}/releases/download/v0.5.0/`;
const release = (over = {}) => ({
  tag_name: 'v0.5.0', draft: false, prerelease: false, body: 'Nouveautés\r\n- truc',
  assets: [
    { name: 'Japp-Setup-0.5.0.exe', size: 1000, browser_download_url: DL + 'Japp-Setup-0.5.0.exe' },
    { name: 'SHA256SUMS.txt', size: 100, browser_download_url: DL + 'SHA256SUMS.txt' },
  ], ...over,
});

test('comparaison de versions', () => {
  assert.ok(u.compareVersions('0.10.0', '0.9.9') > 0);
  assert.ok(u.compareVersions('v1.0.0', '0.99.99') > 0);
  assert.equal(u.compareVersions('0.4.0', '0.4.0'), 0);
  assert.ok(u.compareVersions('0.3.9', '0.4.0') < 0);
  assert.equal(u.compareVersions('0.4.0-beta', '0.4.0'), null);
  assert.equal(u.compareVersions('abc', '0.4.0'), null);
});

test('release valide acceptée', () => {
  const r = u.parseRelease(release(), REPO);
  assert.equal(r.version, '0.5.0');
  assert.equal(r.exe.name, 'Japp-Setup-0.5.0.exe');
  assert.equal(r.htmlUrl, `https://github.com/${REPO}/releases/tag/v0.5.0`);
  assert.ok(!r.notes.includes('\r'));
});

test('releases refusées : brouillon, préversion, étiquette bizarre, fichiers hors dépôt, nom incohérent', () => {
  assert.equal(u.parseRelease(release({ draft: true }), REPO), null);
  assert.equal(u.parseRelease(release({ prerelease: true }), REPO), null);
  assert.equal(u.parseRelease(release({ tag_name: 'v0.5.0-beta.1' }), REPO), null);
  assert.equal(u.parseRelease(release({ tag_name: '0.5.0' }), REPO), null);
  assert.equal(u.parseRelease(null, REPO), null);
  const evil = release();
  evil.assets[0].browser_download_url = 'https://evil.example/Japp-Setup-0.5.0.exe';
  assert.equal(u.parseRelease(evil, REPO), null);
  const other = release();
  other.assets[0].browser_download_url = `https://github.com/autre/depot/releases/download/v0.5.0/Japp-Setup-0.5.0.exe`;
  assert.equal(u.parseRelease(other, REPO), null);
  const mismatch = release();
  mismatch.assets[0].name = 'Japp-Setup-0.9.9.exe';
  mismatch.assets[0].browser_download_url = DL + 'Japp-Setup-0.9.9.exe';
  assert.equal(u.parseRelease(mismatch, REPO), null);
  const noSums = release({ assets: [release().assets[0]] });
  assert.equal(u.parseRelease(noSums, REPO), null);
});

test('hôtes autorisés', () => {
  assert.ok(u.isAllowedHost('https://github.com/x'));
  assert.ok(u.isAllowedHost('https://release-assets.githubusercontent.com/x'));
  assert.ok(!u.isAllowedHost('http://github.com/x'));
  assert.ok(!u.isAllowedHost('https://github.com.evil.example/x'));
  assert.ok(!u.isAllowedHost('https://evilgithubusercontent.com/x'));
  assert.ok(!u.isAllowedHost('file:///C:/x'));
});

test('lecture de SHA256SUMS.txt', () => {
  const h = 'a'.repeat(64), g = 'b'.repeat(64);
  assert.equal(u.expectedHash(`${h}  Japp-Setup-0.5.0.exe\n${g}  autre.txt\n`, 'Japp-Setup-0.5.0.exe'), h);
  assert.equal(u.expectedHash(`${h.toUpperCase()} *dir/Japp-Setup-0.5.0.exe\r\n`, 'Japp-Setup-0.5.0.exe'), h);
  assert.equal(u.expectedHash(`${h}  autre.exe`, 'Japp-Setup-0.5.0.exe'), null);
  assert.equal(u.expectedHash('pas un hash  Japp-Setup-0.5.0.exe', 'Japp-Setup-0.5.0.exe'), null);
});

// --- faux serveur : API, somme, installateur ---
function server(handler) {
  return new Promise((resolve) => {
    const srv = http.createServer(handler).listen(0, '127.0.0.1', () => resolve({ srv, base: `http://127.0.0.1:${srv.address().port}` }));
  });
}
const deps = (base) => ({ allow: (url) => url.startsWith(base) });

test('checkLatest : nouvelle version détectée, ou non', async (t) => {
  const { srv, base } = await server((req, res) => res.end(JSON.stringify(release())));
  t.after(() => srv.close());
  const d = { ...deps(base), apiUrl: base + '/latest' };
  assert.equal((await u.checkLatest({ repo: REPO, current: '0.4.0', deps: d })).newer, true);
  assert.equal((await u.checkLatest({ repo: REPO, current: '0.5.0', deps: d })).newer, false);
  assert.equal((await u.checkLatest({ repo: REPO, current: '0.6.0', deps: d })).newer, false);
});

test('checkLatest : erreur HTTP remontée', async (t) => {
  const { srv, base } = await server((req, res) => { res.statusCode = 403; res.end('{}'); });
  t.after(() => srv.close());
  await assert.rejects(u.checkLatest({ repo: REPO, current: '0.4.0', deps: { ...deps(base), apiUrl: base + '/x' } }), /HTTP 403/);
});

function dlServer(payload, sumsHash) {
  return server((req, res) => {
    if (req.url === '/redir') { res.statusCode = 302; res.setHeader('Location', '/exe'); return res.end(); }
    if (req.url === '/sums') return res.end(`${sumsHash}  Japp-Setup-0.5.0.exe\n`);
    if (req.url === '/exe') { res.setHeader('Content-Length', payload.length); return res.end(payload); }
    res.statusCode = 404; res.end();
  });
}
const sha = (b) => crypto.createHash('sha256').update(b).digest('hex');

test('téléchargement : conservé si le SHA-256 correspond (redirection suivie, progression signalée)', async (t) => {
  const payload = crypto.randomBytes(300_000);
  const { srv, base } = await dlServer(payload, sha(payload));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'japp-upd-'));
  t.after(() => { srv.close(); fs.rmSync(dir, { recursive: true, force: true }); });
  const info = { exe: { name: 'Japp-Setup-0.5.0.exe', url: base + '/redir', size: payload.length }, sumsUrl: base + '/sums' };
  const seen = [];
  const file = await u.downloadVerified({ info, destDir: dir, onProgress: (f) => seen.push(f), deps: deps(base) });
  assert.equal(file, path.join(dir, 'Japp-Setup-0.5.0.exe'));
  assert.deepEqual(fs.readFileSync(file), payload);
  assert.ok(seen.length && Math.max(...seen) <= 1.0001 && seen.at(-1) > 0.99);
  assert.ok(!fs.existsSync(file + '.part'));
});

test('téléchargement : fichier SUPPRIMÉ si le SHA-256 ne correspond pas', async (t) => {
  const payload = crypto.randomBytes(50_000);
  const { srv, base } = await dlServer(payload, 'f'.repeat(64));
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'japp-upd-'));
  t.after(() => { srv.close(); fs.rmSync(dir, { recursive: true, force: true }); });
  const info = { exe: { name: 'Japp-Setup-0.5.0.exe', url: base + '/exe', size: payload.length }, sumsUrl: base + '/sums' };
  await assert.rejects(u.downloadVerified({ info, destDir: dir, deps: deps(base) }), /SHA-256/);
  assert.deepEqual(fs.readdirSync(dir), []);                 // ni installateur ni .part
});

test('téléchargement : refusé sans somme publiée, et vers un hôte non autorisé', async (t) => {
  const payload = Buffer.from('x');
  const { srv, base } = await dlServer(payload, '');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'japp-upd-'));
  t.after(() => { srv.close(); fs.rmSync(dir, { recursive: true, force: true }); });
  const info = { exe: { name: 'Japp-Setup-0.5.0.exe', url: base + '/exe', size: 1 }, sumsUrl: base + '/sums' };
  await assert.rejects(u.downloadVerified({ info, destDir: dir, deps: deps(base) }), /introuvable/);
  await assert.rejects(u.downloadVerified({ info: { ...info, sumsUrl: 'https://evil.example/s' }, destDir: dir }), /non autorisée/);
});

test('préférences : valeurs par défaut et persistance', () => {
  const f = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'japp-pref-')), 'updates.json');
  assert.deepEqual(u.loadPrefs(f), { enabled: true, lastCheck: 0, skipped: '' });
  u.savePrefs(f, { enabled: false, lastCheck: 5, skipped: '0.5.0' });
  assert.deepEqual(u.loadPrefs(f), { enabled: false, lastCheck: 5, skipped: '0.5.0' });
  fs.writeFileSync(f, 'pas du json');
  assert.equal(u.loadPrefs(f).enabled, true);
});
