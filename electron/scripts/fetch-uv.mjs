// Télécharge uv (gestionnaire Python utilisé au premier lancement) et vérifie son empreinte SHA-256.
// La version et l'empreinte sont épinglées : un binaire modifié en route fait échouer le build.
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync, existsSync, rmSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const UV_VERSION = '0.13.1';
const UV_SHA256 = '3b2661a463a5baea7f5076ea2b25ab71d77f36a6c0d809e5350651792f80a672';
const URL = `https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-pc-windows-msvc.zip`;

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, '..', 'build', 'uv');
const exe = join(out, 'uv.exe');

if (existsSync(exe)) {
  console.log('uv.exe déjà présent :', exe);
  process.exit(0);
}

mkdirSync(out, { recursive: true });
console.log('Téléchargement de uv', UV_VERSION);
const res = await fetch(URL, { redirect: 'follow' });
if (!res.ok) throw new Error(`Téléchargement impossible (${res.status})`);
const buf = Buffer.from(await res.arrayBuffer());

const got = createHash('sha256').update(buf).digest('hex');
if (got !== UV_SHA256) throw new Error(`Empreinte SHA-256 inattendue pour uv !\n attendue : ${UV_SHA256}\n obtenue  : ${got}`);

const zip = join(out, 'uv.zip');
writeFileSync(zip, buf);
// tar.exe de Windows (bsdtar) par chemin absolu : le `tar` du PATH peut être GNU tar (Git Bash) qui lit mal « C: ».
const winTar = join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe');
try {
  execFileSync(winTar, ['-xf', zip, '-C', out], { stdio: 'inherit' });
} catch {
  execFileSync('powershell', ['-NoProfile', '-Command', `Expand-Archive -LiteralPath '${zip}' -DestinationPath '${out}' -Force`], { stdio: 'inherit' });
}
rmSync(zip);
if (!existsSync(exe)) throw new Error('uv.exe absent après extraction');
for (const extra of ['uvw.exe', 'uvx.exe']) rmSync(join(out, extra), { force: true });   // seul uv.exe sert
console.log('OK :', exe, `(${(readFileSync(exe).length / 1e6).toFixed(1)} Mo)`);
