// Prépare les ressources embarquées dans l'installateur :
//  - copie l'interface Angular compilée dans build/frontend
//  - copie le backend (sans caches ni données) dans build/backend
//  - copie requirements.txt
import { cpSync, rmSync, mkdirSync, existsSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..', '..');            // racine du dépôt
const build = join(here, '..', 'build');

const dist = join(root, 'frontend', 'dist', 'frontend', 'browser');
if (!existsSync(join(dist, 'index.html'))) throw new Error("Interface non compilée : lance d'abord `npm run build` dans frontend/");

for (const d of ['frontend', 'backend']) rmSync(join(build, d), { recursive: true, force: true });
mkdirSync(build, { recursive: true });
cpSync(dist, join(build, 'frontend'), { recursive: true });
cpSync(join(root, 'backend'), join(build, 'backend'), {
  recursive: true,
  filter: (src) => !/__pycache__|\.pyc$|\.pytest_cache|[\\/]tests([\\/]|$)/.test(src),
});
cpSync(join(root, 'requirements.txt'), join(build, 'requirements.txt'));
console.log('Ressources prêtes dans', build);
