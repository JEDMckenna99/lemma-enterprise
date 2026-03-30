#!/usr/bin/env node

/**
 * Lemma CDN Build Script
 * 
 * Builds optimized, minified versions of all Lemma scripts for CDN distribution
 * Supports versioning, integrity hashes, and multiple output formats
 */

const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// Build configuration
const BUILD_CONFIG = {
  version: '1.0.0',
  basePath: path.resolve(__dirname, '..'),
  outputPath: path.resolve(__dirname, 'dist'),
  sources: {
    'lemma-wallet': {
      input: 'static/js/lemma-wallet.js',
      minified: true,
      gzip: true,
      brotli: true
    },
    'lemma-session-free-auth': {
      input: 'static/js/lemma-session-free-auth.js',
      minified: true,
      gzip: true,
      brotli: true
    },
    'lemma-verifier': {
      input: 'static/js/lemma-verifier.js',
      minified: true,
      gzip: true,
      brotli: true
    }
  },
  css: {
    'lemma-styles': {
      input: 'static/css/lemma.css',
      minified: true,
      gzip: true,
      brotli: true
    }
  }
};

// Utility functions
function log(message) {
  console.log(`[CDN Build] ${message}`);
}

function error(message) {
  console.error(`[CDN Build ERROR] ${message}`);
}

function ensureDir(dirPath) {
  if (!fs.existsSync(dirPath)) {
    fs.mkdirSync(dirPath, { recursive: true });
  }
}

function minifyJS(content) {
  // Simple minification (for production, use proper minifier like terser)
  return content
    .replace(/\/\*[\s\S]*?\*\//g, '') // Remove block comments
    .replace(/\/\/.*$/gm, '') // Remove line comments
    .replace(/^\s+|\s+$/gm, '') // Remove leading/trailing whitespace
    .replace(/\s+/g, ' ') // Collapse whitespace
    .trim();
}

function minifyCSS(content) {
  return content
    .replace(/\/\*[\s\S]*?\*\//g, '') // Remove comments
    .replace(/^\s+|\s+$/gm, '') // Remove leading/trailing whitespace
    .replace(/\s+/g, ' ') // Collapse whitespace
    .replace(/;\s*}/g, '}') // Remove last semicolon before closing brace
    .replace(/\s*{\s*/g, '{') // Remove spaces around braces
    .replace(/;\s*/g, ';') // Remove spaces after semicolons
    .trim();
}

function calculateIntegrity(content) {
  const crypto = require('crypto');
  const hash = crypto.createHash('sha384').update(content).digest('base64');
  return `sha384-${hash}`;
}

function compressWithGzip(content) {
  const zlib = require('zlib');
  return zlib.gzipSync(content);
}

function compressWithBrotli(content) {
  const zlib = require('zlib');
  return zlib.brotliCompressSync(content);
}

function buildJavaScript() {
  log('Building JavaScript files...');
  
  const jsOutputPath = path.join(BUILD_CONFIG.outputPath, 'js');
  ensureDir(jsOutputPath);
  
  const manifest = {
    version: BUILD_CONFIG.version,
    timestamp: new Date().toISOString(),
    files: {}
  };
  
  for (const [name, config] of Object.entries(BUILD_CONFIG.sources)) {
    const inputPath = path.join(BUILD_CONFIG.basePath, config.input);
    
    if (!fs.existsSync(inputPath)) {
      error(`Source file not found: ${inputPath}`);
      continue;
    }
    
    const content = fs.readFileSync(inputPath, 'utf8');
    
    // Build regular version
    const outputPath = path.join(jsOutputPath, `${name}.js`);
    fs.writeFileSync(outputPath, content);
    
    // Build minified version
    if (config.minified) {
      const minifiedContent = minifyJS(content);
      const minifiedPath = path.join(jsOutputPath, `${name}.min.js`);
      fs.writeFileSync(minifiedPath, minifiedContent);
      
      // Calculate integrity hash
      const integrity = calculateIntegrity(minifiedContent);
      
      // Compress with gzip
      if (config.gzip) {
        const gzipContent = compressWithGzip(minifiedContent);
        const gzipPath = path.join(jsOutputPath, `${name}.min.js.gz`);
        fs.writeFileSync(gzipPath, gzipContent);
      }
      
      // Compress with brotli
      if (config.brotli) {
        const brotliContent = compressWithBrotli(minifiedContent);
        const brotliPath = path.join(jsOutputPath, `${name}.min.js.br`);
        fs.writeFileSync(brotliPath, brotliContent);
      }
      
      // Update manifest
      manifest.files[name] = {
        original: {
          path: `js/${name}.js`,
          size: content.length
        },
        minified: {
          path: `js/${name}.min.js`,
          size: minifiedContent.length,
          integrity: integrity,
          compression: {
            gzip: config.gzip ? `js/${name}.min.js.gz` : null,
            brotli: config.brotli ? `js/${name}.min.js.br` : null
          }
        }
      };
    }
    
    log(`Built ${name} (${content.length} -> ${config.minified ? minifyJS(content).length : content.length} bytes)`);
  }
  
  return manifest;
}

function buildCSS() {
  log('Building CSS files...');
  
  const cssOutputPath = path.join(BUILD_CONFIG.outputPath, 'css');
  ensureDir(cssOutputPath);
  
  const manifest = {
    version: BUILD_CONFIG.version,
    timestamp: new Date().toISOString(),
    files: {}
  };
  
  for (const [name, config] of Object.entries(BUILD_CONFIG.css)) {
    const inputPath = path.join(BUILD_CONFIG.basePath, config.input);
    
    if (!fs.existsSync(inputPath)) {
      error(`CSS file not found: ${inputPath}`);
      continue;
    }
    
    const content = fs.readFileSync(inputPath, 'utf8');
    
    // Build regular version
    const outputPath = path.join(cssOutputPath, `${name}.css`);
    fs.writeFileSync(outputPath, content);
    
    // Build minified version
    if (config.minified) {
      const minifiedContent = minifyCSS(content);
      const minifiedPath = path.join(cssOutputPath, `${name}.min.css`);
      fs.writeFileSync(minifiedPath, minifiedContent);
      
      // Calculate integrity hash
      const integrity = calculateIntegrity(minifiedContent);
      
      // Compress with gzip
      if (config.gzip) {
        const gzipContent = compressWithGzip(minifiedContent);
        const gzipPath = path.join(cssOutputPath, `${name}.min.css.gz`);
        fs.writeFileSync(gzipPath, gzipContent);
      }
      
      // Compress with brotli
      if (config.brotli) {
        const brotliContent = compressWithBrotli(minifiedContent);
        const brotliPath = path.join(cssOutputPath, `${name}.min.css.br`);
        fs.writeFileSync(brotliPath, brotliContent);
      }
      
      // Update manifest
      manifest.files[name] = {
        original: {
          path: `css/${name}.css`,
          size: content.length
        },
        minified: {
          path: `css/${name}.min.css`,
          size: minifiedContent.length,
          integrity: integrity,
          compression: {
            gzip: config.gzip ? `css/${name}.min.css.gz` : null,
            brotli: config.brotli ? `css/${name}.min.css.br` : null
          }
        }
      };
    }
    
    log(`Built ${name} CSS (${content.length} -> ${config.minified ? minifyCSS(content).length : content.length} bytes)`);
  }
  
  return manifest;
}

function generateManifest(jsManifest, cssManifest) {
  log('Generating manifest...');
  
  const manifest = {
    version: BUILD_CONFIG.version,
    timestamp: new Date().toISOString(),
    baseUrl: 'https://cdn.lemma.id/', // Will be updated based on deployment
    javascript: jsManifest.files,
    css: cssManifest.files,
    examples: {
      basicIntegration: `
<!-- Basic Lemma Integration -->
<script src="https://cdn.lemma.id/js/lemma-auto.min.js" 
        integrity="${jsManifest.files['lemma-auto']?.minified?.integrity}"
        crossorigin="anonymous"></script>
<div data-lemma-verify="auto" 
     data-lemma-credential-type="identity">
  <p>Loading verification...</p>
</div>
      `.trim(),
      
      withCSS: `
<!-- Lemma with Styling -->
<link rel="stylesheet" 
      href="https://cdn.lemma.id/css/lemma-styles.min.css"
      integrity="${cssManifest.files['lemma-styles']?.minified?.integrity}"
      crossorigin="anonymous">
<script src="https://cdn.lemma.id/js/lemma-auto.min.js" 
        integrity="${jsManifest.files['lemma-auto']?.minified?.integrity}"
        crossorigin="anonymous"></script>
      `.trim(),
      
      selfHosted: `
<!-- Self-hosted version -->
<script src="/static/js/lemma-auto.min.js"></script>
<div data-lemma-verify="auto" data-lemma-api-key="your-api-key">
  <!-- Your credential verification content -->
</div>
      `.trim()
    }
  };
  
  const manifestPath = path.join(BUILD_CONFIG.outputPath, 'manifest.json');
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
  
  log(`Manifest generated: ${manifestPath}`);
  return manifest;
}

function generateReadme() {
  log('Generating README...');
  
  const readme = `# Lemma CDN Distribution

This directory contains the CDN-ready builds of all Lemma verification scripts.

## Quick Start

### Basic Integration (Auto-detection)
\`\`\`html
<script src="https://cdn.lemma.id/js/lemma-auto.min.js" 
        integrity="sha384-..." 
        crossorigin="anonymous"></script>
<div data-lemma-verify="auto">
  <p>Loading verification...</p>
</div>
\`\`\`

### With Styling
\`\`\`html
<link rel="stylesheet" 
      href="https://cdn.lemma.id/css/lemma-styles.min.css"
      integrity="sha384-..." 
      crossorigin="anonymous">
<script src="https://cdn.lemma.id/js/lemma-auto.min.js" 
        integrity="sha384-..." 
        crossorigin="anonymous"></script>
\`\`\`

## Available Files

### JavaScript
- \`lemma-auto.js\` / \`lemma-auto.min.js\` - Auto-integration script
- \`lemma-verification-flow.js\` / \`lemma-verification-flow.min.js\` - Verification flow components
- \`lemma-shield-inline.js\` / \`lemma-shield-inline.min.js\` - Inline shield components

### CSS
- \`lemma-styles.css\` / \`lemma-styles.min.css\` - Core Lemma styles
- \`stripe-design.css\` / \`stripe-design.min.css\` - Stripe design system

### Compression
All minified files are available in:
- \`.gz\` (gzip compression)
- \`.br\` (brotli compression)

## Integrity Verification

All files include SHA-384 integrity hashes for security. Check \`manifest.json\` for current hashes.

## Version Information

- Version: ${BUILD_CONFIG.version}
- Build Date: ${new Date().toISOString()}
- Environment: Production

## Self-Hosting

To self-host these files:

1. Download the entire \`dist/\` directory
2. Host on your CDN or static file server
3. Update script \`src\` attributes to point to your hosting location
4. Ensure proper CORS headers for cross-origin requests

## Performance Notes

- All files are optimized for production
- Gzip compression reduces file sizes by ~70%
- Brotli compression reduces file sizes by ~75%
- Use HTTP/2 for optimal performance
- Enable caching headers for better performance

## Support

For issues or questions about CDN distribution:
- Check the manifest.json for current file information
- Verify integrity hashes match
- Ensure proper CORS configuration
- Use the unminified versions for debugging

Built with Lemma CDN Build System v${BUILD_CONFIG.version}
`;
  
  const readmePath = path.join(BUILD_CONFIG.outputPath, 'README.md');
  fs.writeFileSync(readmePath, readme);
  
  log(`README generated: ${readmePath}`);
}

function generateHerokuConfig() {
  log('Generating Heroku configuration...');
  
  // Create Heroku-specific configuration
  const herokuConfig = {
    // Static file serving configuration
    static: {
      directories: [
        {
          path: "/cdn/dist",
          headers: {
            "Cache-Control": "public, max-age=31536000, immutable",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Origin, X-Requested-With, Content-Type, Accept"
          }
        }
      ]
    },
    
    // CDN configuration for Heroku
    cdn: {
      baseUrl: process.env.CDN_BASE_URL || "https://your-app.herokuapp.com/cdn/dist",
      redisUrl: process.env.REDIS_URL,
      compressionEnabled: true,
      cacheTtl: 31536000 // 1 year
    },
    
    // Build configuration
    build: {
      commands: [
        "cd cdn && node build.js"
      ]
    }
  };
  
  const configPath = path.join(BUILD_CONFIG.outputPath, 'heroku-config.json');
  fs.writeFileSync(configPath, JSON.stringify(herokuConfig, null, 2));
  
  // Generate Procfile for Heroku
  const procfile = `web: node app.js
release: cd cdn && node build.js`;
  
  const procfilePath = path.join(BUILD_CONFIG.basePath, 'Procfile.cdn');
  fs.writeFileSync(procfilePath, procfile);
  
  log(`Heroku configuration generated: ${configPath}`);
  log(`Procfile generated: ${procfilePath}`);
}

// Main build function
function build() {
  log('Starting CDN build process...');
  
  // Clean output directory
  if (fs.existsSync(BUILD_CONFIG.outputPath)) {
    fs.rmSync(BUILD_CONFIG.outputPath, { recursive: true, force: true });
  }
  ensureDir(BUILD_CONFIG.outputPath);
  
  // Build JavaScript files
  const jsManifest = buildJavaScript();
  
  // Build CSS files
  const cssManifest = buildCSS();
  
  // Generate manifest
  const manifest = generateManifest(jsManifest, cssManifest);
  
  // Generate documentation
  generateReadme();
  
  // Generate Heroku-specific configuration
  generateHerokuConfig();
  
  // Create version file
  const versionFile = {
    version: BUILD_CONFIG.version,
    buildDate: new Date().toISOString(),
    files: Object.keys(manifest.javascript).length + Object.keys(manifest.css).length
  };
  
  fs.writeFileSync(
    path.join(BUILD_CONFIG.outputPath, 'version.json'),
    JSON.stringify(versionFile, null, 2)
  );
  
  log(`CDN build complete! Output: ${BUILD_CONFIG.outputPath}`);
  log(`Files built: ${Object.keys(manifest.javascript).length} JS, ${Object.keys(manifest.css).length} CSS`);
  log(`Total size reduction: ~${Math.round(((getTotalOriginalSize(manifest) - getTotalMinifiedSize(manifest)) / getTotalOriginalSize(manifest)) * 100)}%`);
}

function getTotalOriginalSize(manifest) {
  let total = 0;
  for (const file of Object.values(manifest.javascript)) {
    total += file.original.size;
  }
  for (const file of Object.values(manifest.css)) {
    total += file.original.size;
  }
  return total;
}

function getTotalMinifiedSize(manifest) {
  let total = 0;
  for (const file of Object.values(manifest.javascript)) {
    total += file.minified.size;
  }
  for (const file of Object.values(manifest.css)) {
    total += file.minified.size;
  }
  return total;
}

// Run build if called directly
if (require.main === module) {
  build();
}

module.exports = { build, BUILD_CONFIG }; 