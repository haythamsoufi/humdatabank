/**
 * Copy the tinymce npm package into app/static so the editor loads same-origin
 * (avoids browser Tracking Prevention / third-party storage warnings for cdnjs).
 * Run: npm run vendor:tinymce
 */
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const src = path.join(root, 'node_modules', 'tinymce');
const dest = path.join(root, 'app', 'static', 'libs', 'tinymce');

if (!fs.existsSync(src)) {
  console.error('Missing', src, '— run: npm install');
  process.exit(1);
}
fs.rmSync(dest, { recursive: true, force: true });
fs.mkdirSync(dest, { recursive: true });
['tinymce.min.js', 'license.txt'].forEach((f) => {
  fs.copyFileSync(path.join(src, f), path.join(dest, f));
});
['icons', 'models', 'plugins', 'skins', 'themes'].forEach((d) => {
  fs.cpSync(path.join(src, d), path.join(dest, d), { recursive: true });
});
console.log('Vendored tinymce →', dest);
