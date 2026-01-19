#!/usr/bin/env node
/**
 * Build script for @lemma/wallet
 * Outputs: CJS, ESM, and UMD bundles
 */

const fs = require('fs');
const path = require('path');

const srcPath = path.join(__dirname, '..', 'src', 'index.js');
const distPath = path.join(__dirname, '..', 'dist');

// Ensure dist directory exists
if (!fs.existsSync(distPath)) {
    fs.mkdirSync(distPath, { recursive: true });
}

// Read source
const source = fs.readFileSync(srcPath, 'utf-8');

// Remove ES module exports for CJS
const cjsSource = source
    .replace(/^export \{ LemmaWallet \};$/m, '')
    .replace(/^export default LemmaWallet;$/m, 'module.exports = LemmaWallet;\nmodule.exports.LemmaWallet = LemmaWallet;\nmodule.exports.default = LemmaWallet;');

// ESM version (keep as is, just clean up)
const esmSource = source;

// UMD version for browsers
const umdSource = `(function(root, factory) {
    if (typeof define === 'function' && define.amd) {
        define([], factory);
    } else if (typeof module === 'object' && module.exports) {
        module.exports = factory();
    } else {
        root.LemmaWallet = factory().LemmaWallet;
        root.lemmaWallet = new root.LemmaWallet();
    }
}(typeof self !== 'undefined' ? self : this, function() {
'use strict';

${source
    .replace(/^export \{ LemmaWallet \};$/m, '')
    .replace(/^export default LemmaWallet;$/m, '')}

return { LemmaWallet, default: LemmaWallet };
}));
`;

// Write outputs
fs.writeFileSync(path.join(distPath, 'lemma-wallet.js'), cjsSource);
fs.writeFileSync(path.join(distPath, 'lemma-wallet.esm.js'), esmSource);
fs.writeFileSync(path.join(distPath, 'lemma-wallet.umd.js'), umdSource);

// Copy type definitions
fs.copyFileSync(
    path.join(__dirname, '..', 'src', 'index.d.ts'),
    path.join(distPath, 'index.d.ts')
);

console.log('✅ Build complete:');
console.log('   - dist/lemma-wallet.js (CommonJS)');
console.log('   - dist/lemma-wallet.esm.js (ES Modules)');
console.log('   - dist/lemma-wallet.umd.js (UMD/Browser)');
console.log('   - dist/index.d.ts (TypeScript)');

// Optionally minify if terser is available
try {
    const { minify } = require('terser');
    
    (async () => {
        const minified = await minify(umdSource, {
            compress: true,
            mangle: true,
            format: { comments: false }
        });
        
        fs.writeFileSync(path.join(distPath, 'lemma-wallet.min.js'), minified.code);
        console.log('   - dist/lemma-wallet.min.js (Minified)');
    })();
} catch (e) {
    console.log('   (terser not installed, skipping minification)');
}
