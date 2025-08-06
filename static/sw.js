// Lemma Service Worker - Minimal Implementation
// This prevents service worker errors and provides basic caching

const CACHE_NAME = 'lemma-v1';
const STATIC_ASSETS = [
  '/static/css/lemma-design-system.css',
  '/static/js/lemma-federated-wallet.js',
  '/static/js/lemma-bot-shield-simple.js',
  '/static/img/lemma_logo.svg'
];

// Install event - cache static assets
self.addEventListener('install', event => {
  console.log('[SW] Installing service worker');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('[SW] Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .catch(err => {
        console.log('[SW] Cache install failed:', err);
      })
  );
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener('activate', event => {
  console.log('[SW] Activating service worker');
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== CACHE_NAME) {
            console.log('[SW] Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
  self.clients.claim();
});

// Fetch event - serve from cache, fallback to network
self.addEventListener('fetch', event => {
  // Skip non-GET requests and external URLs
  if (event.request.method !== 'GET' || !event.request.url.startsWith(self.location.origin)) {
    return;
  }

  // Skip Cloudflare analytics and other external scripts
  if (event.request.url.includes('cloudflareinsights.com') || 
      event.request.url.includes('beacon.min.js')) {
    console.log('[SW] Skipping external analytics:', event.request.url);
    return;
  }

  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Return cached version if available
        if (response) {
          console.log('[SW] Serving from cache:', event.request.url);
          return response;
        }

        // Fallback to network
        console.log('[SW] Fetching from network:', event.request.url);
        return fetch(event.request)
          .then(response => {
            // Cache successful responses for static assets
            if (response.status === 200 && STATIC_ASSETS.some(asset => event.request.url.endsWith(asset))) {
              const responseToCache = response.clone();
              caches.open(CACHE_NAME)
                .then(cache => {
                  cache.put(event.request, responseToCache);
                });
            }
            return response;
          })
          .catch(err => {
            console.log('[SW] Network fetch failed:', err);
            throw err;
          });
      })
  );
});

// Handle service worker errors
self.addEventListener('error', event => {
  console.log('[SW] Service worker error:', event.error);
});

self.addEventListener('unhandledrejection', event => {
  console.log('[SW] Unhandled promise rejection:', event.reason);
  event.preventDefault();
});