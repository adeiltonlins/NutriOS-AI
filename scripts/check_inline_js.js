const fs = require('fs');
const path = require('path');
const root = path.join(__dirname, '..', 'app', 'static');
let failed = false;
for (const file of fs.readdirSync(root).filter(name => name.endsWith('.html'))) {
  const html = fs.readFileSync(path.join(root, file), 'utf8');
  for (const [, source] of html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/gi)) {
    try { new Function(source); }
    catch (error) { failed = true; console.error(`${file}: ${error.message}`); }
  }
}
if (failed) process.exit(1);
console.log('JavaScript inline válido.');
