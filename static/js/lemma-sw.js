/**
 * Lemma Service Worker v1.0
 * 
 * LOCAL-FIRST CACHING
 * 
 * This service worker enables true offline-first authentication by caching:
 * - Wallet bridge HTML (for cross-site wallet access)
 * - Wallet SDK JavaScript
 * - Public keys for local Ed25519 verification
 * 
 * NETWORK CALL IMPACT:
 * - First visit: 3-4 network calls (bridge, SDK, keys, revocations)
 * - Subsequent visits: 0 network calls (everything from cache)
 * - Offline: Still works! Verification is local.
 */

const CACHE_NAME = 'lemma-wallet-v1';
const CACHE_VERSION = '1.0.0';

// Assets to cache immediately on install
const PRECACHE_ASSETS = [
    '/wallet/bridge',
    '/static/js/lemma-wallet.js',
    '/static/js/lemma-iam-sdk.js'
];

// Assets to cache on first use
const RUNTIME_CACHE_PATTERNS = [
    /\/api\/v1\/revocation\/(list|bloom)/,
    /\/\.well-known\/lemma-keys\.json/
];

// ============================================
// INSTALL - Precache essential assets
// ============================================

self.addEventListener('install', (event) => {
    console.log('[Lemma SW] Installing v' + CACHE_VERSION);
    
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            console.log('[Lemma SW] Precaching essential assets');
            return cache.addAll(PRECACHE_ASSETS);
        }).then(() => {
            // Activate immediately, don't wait for old SW to finish
            return self.skipWaiting();
        })
    );
});

// ============================================
// ACTIVATE - Clean up old caches
// ============================================

self.addEventListener('activate', (event) => {
    console.log('[Lemma SW] Activating v' + CACHE_VERSION);
    
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames
                    .filter((name) => name.startsWith('lemma-') && name !== CACHE_NAME)
                    .map((name) => {
                        console.log('[Lemma SW] Deleting old cache:', name);
                        return caches.delete(name);
                    })
            );
        }).then(() => {
            // Take control of all clients immediately
            return self.clients.claim();
        })
    );
});

// ============================================
// FETCH - Serve from cache, update in background
// ============================================

self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    
    // Only handle same-origin requests or lemma.id
    if (!url.origin.includes('lemma.id') && url.origin !== self.location.origin) {
        return;
    }
    
    // Determine caching strategy based on request
    if (shouldCacheFirst(url)) {
        // CACHE FIRST: Serve cached version immediately, update in background
        event.respondWith(cacheFirst(event.request));
    } else if (shouldRuntimeCache(url)) {
        // STALE-WHILE-REVALIDATE: Serve cached, fetch fresh in background
        event.respondWith(staleWhileRevalidate(event.request));
    }
    // Otherwise, let the browser handle normally (network-first)
});

// ============================================
// CACHING STRATEGIES
// ============================================

/**
 * Determine if request should use cache-first strategy
 */
function shouldCacheFirst(url) {
    // Bridge HTML - heavily cached
    if (url.pathname === '/wallet/bridge') {
        return true;
    }
    
    // Static JS files
    if (url.pathname.startsWith('/static/js/lemma-')) {
        return true;
    }
    
    return false;
}

/**
 * Determine if request should be runtime-cached
 */
function shouldRuntimeCache(url) {
    return RUNTIME_CACHE_PATTERNS.some(pattern => pattern.test(url.pathname));
}

/**
 * Cache-first strategy with background update
 * Best for: Static assets that change infrequently (bridge, SDK)
 */
async function cacheFirst(request) {
    const cache = await caches.open(CACHE_NAME);
    const cachedResponse = await cache.match(request);
    
    if (cachedResponse) {
        // Serve from cache immediately
        console.log('[Lemma SW] Cache hit:', request.url);
        
        // Update cache in background (don't block response)
        updateCacheInBackground(request, cache);
        
        return cachedResponse;
    }
    
    // Not in cache, fetch from network
    console.log('[Lemma SW] Cache miss, fetching:', request.url);
    try {
        const networkResponse = await fetch(request);
        
        if (networkResponse.ok) {
            // Clone and cache the response
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        console.error('[Lemma SW] Fetch failed:', error);
        // Return offline fallback if available
        return new Response('Offline', { status: 503 });
    }
}

/**
 * Stale-while-revalidate strategy
 * Best for: Data that should be fresh but can tolerate stale (revocations)
 */
async function staleWhileRevalidate(request) {
    const cache = await caches.open(CACHE_NAME);
    const cachedResponse = await cache.match(request);
    
    // Fetch fresh version in parallel
    const fetchPromise = fetch(request).then((networkResponse) => {
        if (networkResponse.ok) {
            cache.put(request, networkResponse.clone());
        }
        return networkResponse;
    }).catch((error) => {
        console.warn('[Lemma SW] Network fetch failed:', error);
        return cachedResponse || new Response('Offline', { status: 503 });
    });
    
    // Return cached response immediately if available
    return cachedResponse || fetchPromise;
}

/**
 * Update cache in background without blocking
 */
function updateCacheInBackground(request, cache) {
    // Use a timeout to avoid blocking the main response
    setTimeout(async () => {
        try {
            const networkResponse = await fetch(request);
            if (networkResponse.ok) {
                cache.put(request, networkResponse.clone());
                console.log('[Lemma SW] Background cache update:', request.url);
            }
        } catch (e) {
            // Silently fail - we already served from cache
        }
    }, 100);
}

// ============================================
// MESSAGE HANDLING - For SDK communication
// ============================================

self.addEventListener('message', (event) => {
    const { type, payload } = event.data || {};
    
    switch (type) {
        case 'SKIP_WAITING':
            self.skipWaiting();
            break;
            
        case 'GET_CACHE_STATUS':
            getCacheStatus().then((status) => {
                event.ports[0].postMessage(status);
            });
            break;
            
        case 'CLEAR_CACHE':
            caches.delete(CACHE_NAME).then(() => {
                event.ports[0].postMessage({ success: true });
            });
            break;
            
        case 'PRECACHE_ASSETS':
            caches.open(CACHE_NAME).then((cache) => {
                return cache.addAll(payload.urls || PRECACHE_ASSETS);
            }).then(() => {
                event.ports[0].postMessage({ success: true });
            }).catch((error) => {
                event.ports[0].postMessage({ success: false, error: error.message });
            });
            break;
    }
});

/**
 * Get cache status for debugging/monitoring
 */
async function getCacheStatus() {
    const cache = await caches.open(CACHE_NAME);
    const keys = await cache.keys();
    
    const entries = await Promise.all(
        keys.map(async (request) => {
            const response = await cache.match(request);
            return {
                url: request.url,
                cached: true,
                size: response?.headers.get('content-length') || 'unknown'
            };
        })
    );
    
    return {
        cacheName: CACHE_NAME,
        version: CACHE_VERSION,
        entries: entries,
        count: entries.length
    };
}

console.log('[Lemma SW] Service Worker loaded v' + CACHE_VERSION);
