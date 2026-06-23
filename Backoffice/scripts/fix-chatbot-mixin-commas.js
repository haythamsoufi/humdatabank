const fs = require('fs');
const path = require('path');

const dir = path.join(__dirname, '../app/static/js/chatbot');
const files = fs.readdirSync(dir).filter((f) => f.endsWith('.js') && f !== 'main.js' && f !== 'structured-payloads.js' && f !== 'core.js');

function fix(content) {
    let c = content;
    c = c.replace(/\n    \}\n,/g, '\n    },');
    c = c.replace(/(\n    \}\n)(\n    \/\*\*)/g, '$1,$2');
    c = c.replace(/(\n    \}\n)(\n    \/\/)/g, '$1,$2');
    c = c.replace(/ \*\/,/g, ' */');
    return c;
}

for (const f of files) {
    const p = path.join(dir, f);
    const orig = fs.readFileSync(p, 'utf8');
    const next = fix(orig);
    if (next !== orig) {
        fs.writeFileSync(p, next);
        console.log('fixed', f);
    }
}
