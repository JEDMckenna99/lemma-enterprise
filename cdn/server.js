/**
 * Lemma CDN Server
 * 
 * Simple Express server for serving CDN distribution files
 * Optimized for Heroku deployment with Redis caching
 */

const express = require('express');
const path = require('path');
const fs = require('fs');
const compression = require('compression');
const helmet = require('helmet');
const cors = require('cors');

const app = express();
const PORT = process.env.PORT || 3000;

// Load configuration
const config = JSON.parse(fs.readFileSync(path.join(__dirname, 'dist/heroku-config.json')));
const manifest = JSON.parse(fs.readFileSync(path.join(__dirname, 'dist/manifest.json')));

// Security middleware
app.use(helmet({
  contentSecurityPolicy: false, // Allow embedding in other sites
  crossOriginEmbedderPolicy: false
}));

// CORS configuration for CDN
app.use(cors({
  origin: '*',
  methods: ['GET', 'HEAD', 'OPTIONS'],
  allowedHeaders: ['Origin', 'X-Requested-With', 'Content-Type', 'Accept', 'Authorization'],
  credentials: false
}));

// Compression middleware
app.use(compression({
  filter: (req, res) => {
    if (req.headers['x-no-compression']) {
      return false;
    }
    return compression.filter(req, res);
  }
}));

// Static file serving with CDN headers
app.use('/cdn/dist', express.static(path.join(__dirname, 'dist'), {
  maxAge: '1y',
  immutable: true,
  setHeaders: (res, path, stat) => {
    // Set CDN-specific headers
    res.set('Cache-Control', 'public, max-age=31536000, immutable');
    res.set('Access-Control-Allow-Origin', '*');
    res.set('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
    res.set('Access-Control-Allow-Headers', 'Origin, X-Requested-With, Content-Type, Accept');
    
    // Set compression headers based on file extension
    if (path.endsWith('.gz')) {
      res.set('Content-Encoding', 'gzip');
      res.set('Content-Type', getContentType(path.replace('.gz', '')));
    } else if (path.endsWith('.br')) {
      res.set('Content-Encoding', 'br');
      res.set('Content-Type', getContentType(path.replace('.br', '')));
    }
  }
}));

// Helper function to get content type
function getContentType(filePath) {
  if (filePath.endsWith('.js')) {
    return 'application/javascript';
  } else if (filePath.endsWith('.css')) {
    return 'text/css';
  } else if (filePath.endsWith('.json')) {
    return 'application/json';
  } else if (filePath.endsWith('.md')) {
    return 'text/markdown';
  }
  return 'application/octet-stream';
}

// API endpoints
app.get('/api/manifest', (req, res) => {
  res.json(manifest);
});

app.get('/api/version', (req, res) => {
  const version = JSON.parse(fs.readFileSync(path.join(__dirname, 'dist/version.json')));
  res.json(version);
});

app.get('/api/health', (req, res) => {
  res.json({
    status: 'healthy',
    timestamp: new Date().toISOString(),
    version: manifest.version,
    files: {
      javascript: Object.keys(manifest.javascript).length,
      css: Object.keys(manifest.css).length
    }
  });
});

// Documentation endpoint
app.get('/docs', (req, res) => {
  const readme = fs.readFileSync(path.join(__dirname, 'dist/README.md'), 'utf8');
  res.set('Content-Type', 'text/plain');
  res.send(readme);
});

// Integration examples
app.get('/examples', (req, res) => {
  res.json({
    examples: manifest.examples,
    baseUrl: config.cdn.baseUrl,
    documentation: `${req.protocol}://${req.get('host')}/docs`
  });
});

// Default route
app.get('/', (req, res) => {
  res.json({
    name: 'Lemma CDN',
    version: manifest.version,
    description: 'CDN distribution for Lemma verification system',
    endpoints: {
      manifest: '/api/manifest',
      version: '/api/version',
      health: '/api/health',
      docs: '/docs',
      examples: '/examples',
      cdn: '/cdn/dist'
    },
    usage: {
      javascript: {
        auto: `${req.protocol}://${req.get('host')}/cdn/dist/js/lemma-auto.min.js`,
        verification: `${req.protocol}://${req.get('host')}/cdn/dist/js/lemma-verification-flow.min.js`,
        shield: `${req.protocol}://${req.get('host')}/cdn/dist/js/lemma-shield-inline.min.js`
      },
      css: {
        styles: `${req.protocol}://${req.get('host')}/cdn/dist/css/lemma-styles.min.css`,
        stripe: `${req.protocol}://${req.get('host')}/cdn/dist/css/stripe-design.min.css`
      }
    }
  });
});

// Error handling
app.use((err, req, res, next) => {
  console.error('CDN Server Error:', err);
  res.status(500).json({
    error: 'Internal Server Error',
    message: process.env.NODE_ENV === 'development' ? err.message : 'Something went wrong'
  });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({
    error: 'Not Found',
    message: 'The requested resource was not found',
    availableEndpoints: [
      '/api/manifest',
      '/api/version',
      '/api/health',
      '/docs',
      '/examples',
      '/cdn/dist'
    ]
  });
});

// Redis integration (if available)
if (process.env.REDIS_URL) {
  const redis = require('redis');
  const client = redis.createClient(process.env.REDIS_URL);
  
  client.on('error', (err) => {
    console.warn('Redis connection error:', err);
  });
  
  // Cache middleware for API responses
  const cache = (duration) => (req, res, next) => {
    const key = `cdn:${req.originalUrl}`;
    
    client.get(key, (err, result) => {
      if (err) {
        console.warn('Redis get error:', err);
        return next();
      }
      
      if (result) {
        return res.json(JSON.parse(result));
      }
      
      // Store original json method
      const originalJson = res.json;
      res.json = function(data) {
        client.setex(key, duration, JSON.stringify(data));
        return originalJson.call(this, data);
      };
      
      next();
    });
  };
  
  // Apply caching to API endpoints
  app.get('/api/manifest', cache(300)); // 5 minutes
  app.get('/api/version', cache(3600)); // 1 hour
  app.get('/api/health', cache(60)); // 1 minute
}

// Start server
app.listen(PORT, () => {
  console.log(`[CDN Server] Running on port ${PORT}`);
  console.log(`[CDN Server] Serving files from: ${path.join(__dirname, 'dist')}`);
  console.log(`[CDN Server] Base URL: http://localhost:${PORT}`);
  console.log(`[CDN Server] Health check: http://localhost:${PORT}/api/health`);
  console.log(`[CDN Server] Documentation: http://localhost:${PORT}/docs`);
});

module.exports = app; 