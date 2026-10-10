// Falla si el bundle compilado contiene claves de respuesta o campos privados del banco.
// Uso: node scripts/check-bundle.mjs dist
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join } from 'node:path';

const FORBIDDEN = [
  /is_correct/i,
  /isCorrect/,
  /correct_option_id/i,
  /correctOptionId/,
  /\brationale\b/i,
  /source_page/i,
  /MIGRATION_DATABASE_URL|DATABASE_URL/,
];

const root = process.argv[2] ?? 'dist';
// Chunks del panel docente (carga diferida, solo tras iniciar sesión como docente): pueden nombrar
// campos de revisión como "rationale", pero nunca contienen datos del banco. Se revisan solo por secretos.
const TEACHER_CHUNK = /AdminPage-[\w-]+\.js$/;
const SECRET_ONLY = [/MIGRATION_DATABASE_URL|DATABASE_URL/];
const files = [];
(function walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p);
    else if (/\.(js|mjs|html|json|css|map)$/.test(name)) files.push(p);
  }
})(root);

const hits = [];
for (const f of files) {
  const text = readFileSync(f, 'utf8');
  const rules = TEACHER_CHUNK.test(f) ? SECRET_ONLY : FORBIDDEN;
  for (const re of rules) if (re.test(text)) hits.push(`${f}: ${re}`);
}
if (files.length === 0) {
  console.error(`check-bundle: no hay archivos en ${root}; ¿ejecutaste el build?`);
  process.exit(2);
}
if (hits.length) {
  console.error('check-bundle: contenido prohibido en el bundle:\n' + hits.join('\n'));
  process.exit(1);
}
console.log(`check-bundle: OK (${files.length} archivos revisados)`);
