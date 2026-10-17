// Test d'intégration du bootstrap : crée un VRAI petit environnement Python avec uv (internet requis).
// Lancé par `npm test` ; nécessite build/uv/uv.exe (node scripts/fetch-uv.mjs).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { ensureEnv, isReady, pythonPath } = require('../bootstrap');

const UV = path.join(__dirname, '..', 'build', 'uv', 'uv.exe');

test('crée un environnement, puis le réutilise sans le recréer', { timeout: 300_000 }, async (t) => {
  if (!fs.existsSync(UV)) return t.skip('uv.exe absent — lance `node scripts/fetch-uv.mjs`');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'japp-boot-'));
  t.after(() => fs.rmSync(tmp, { recursive: true, force: true }));

  const req = path.join(tmp, 'requirements.txt');
  fs.writeFileSync(req, '# test\nidna==3.10\n');
  const envDir = path.join(tmp, 'env');
  const statuses = [];
  const opts = { uvPath: UV, requirementsPath: req, envDir, cacheDir: path.join(tmp, 'cache'), onStatus: (s, p) => statuses.push([s, p]) };

  assert.equal(isReady(envDir, req), false);
  const py = await ensureEnv(opts);
  assert.equal(py, pythonPath(envDir));
  assert.ok(fs.existsSync(py), 'python.exe doit exister');
  assert.equal(isReady(envDir, req), true);
  assert.equal(statuses.at(-1)[1], 100);
  assert.ok(!fs.existsSync(opts.cacheDir), 'le cache de téléchargement est supprimé');

  const before = statuses.length;
  await ensureEnv(opts);                                  // 2e appel : rien à faire
  assert.equal(statuses.length, before);

  fs.writeFileSync(req, '# test\nidna==3.11\n');          // requirements modifié -> environnement obsolète
  assert.equal(isReady(envDir, req), false);
});

test('échoue clairement si uv est introuvable', async () => {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'japp-boot-'));
  const req = path.join(tmp, 'r.txt');
  fs.writeFileSync(req, 'idna==3.10\n');
  await assert.rejects(
    ensureEnv({ uvPath: path.join(tmp, 'nope.exe'), requirementsPath: req, envDir: path.join(tmp, 'e'), cacheDir: path.join(tmp, 'c'), onStatus: () => {} }),
    /uv introuvable/);
  fs.rmSync(tmp, { recursive: true, force: true });
});
