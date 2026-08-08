const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '../..');
const srcDir = path.join(root, 'node_modules', 'gridstack', 'dist');
const destDir = path.join(root, 'app', 'static', 'libs', 'gridstack');

const files = ['gridstack.min.js', 'gridstack.min.css', 'gridstack-all.js'];

if (!fs.existsSync(srcDir)) {
  console.error('Run npm install first — gridstack dist not found.');
  process.exit(1);
}

fs.mkdirSync(destDir, { recursive: true });
for (const file of files) {
  const src = path.join(srcDir, file);
  if (!fs.existsSync(src)) continue;
  fs.copyFileSync(src, path.join(destDir, file));
  console.log('Copied', file);
}
