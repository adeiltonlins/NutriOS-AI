/**
 * NutriOS Service Worker — PWA offline support
 * Cache strategy: Stale-while-revalidate for assets, network-first for API
 */
const CACHE_NAME = 'nutrios-v28';
const STATIC_ASSETS = [
  '/app',
  '/static/nutrios-dashboard-v6.css',
  '/static/nutrios-dashboard-v7.css',
  '/static/nutrios-analytics-v14.css',
  '/static/nutrios-v22-unified.css',
  '/static/nutrios-v23-polish.css',
  '/static/nutrios-v24-final.css',
  '/static/nutrios-v25-final.css',
  '/static/nutrios-datetime.css',
  '/static/nutrios-v26-refine.css',
  '/static/nutrios-v27-polish.css',
  '/static/nutrios-v28-clinical-flow.css',
  '/static/nutrios-design-system-v1.css',
  '/static/nutrios-v24-theme.js',
  '/static/nutrios-datetime.js',
  '/static/manifest.json',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png'
];

const API_CACHE_NAME = 'nutrios-api-v28';
const API_PATTERNS = [
  /^\/api\/me/,
  /^\/app\/api\/dashboard-clinico/,
  /^\/app\/api\/pacientes/,
  /^\/app\/api\/configuracoes/,
  /^\/paciente\/api\//
];

// Install — cache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// Activate — clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME && k !== API_CACHE_NAME)
            .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// Fetch — stale-while-revalidate for static, network-first for API
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  const isApi = API_PATTERNS.some(p => p.test(url.pathname));
  const isStatic = url.pathname.startsWith('/static/') || url.pathname === '/app' || url.pathname === '/';

  // Skip non-GET and cross-origin
  if (event.request.method !== 'GET' || url.origin !== location.origin) return;

  if (isApi) {
    // Network-first for API — fresh data critical
    event.respondWith(networkFirstThenCache(event.request, API_CACHE_NAME));
  } else if (isStatic) {
    // Stale-while-revalidate for static assets
    event.respondWith(staleWhileRevalidate(event.request, CACHE_NAME));
  }
});

// Network-first strategy
async function networkFirstThenCache(request, cacheName) {
  const cache = await caches.open(cacheName);
  try {
    const response = await fetch(request);
    if (response.ok) {
      cache.put(request, response.clone());
    }
    return response;
  } catch (err) {
    const cached = await cache.match(request);
    if (cached) return cached;
    // Offline fallback for API
    return new Response(JSON.stringify({ error: 'offline', message: 'Você está offline. Alguns dados podem estar desatualizados.' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

// Stale-while-revalidate strategy
async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  const fetchPromise = fetch(request).then(response => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  }).catch(() => cached); // fallback to cache on network error

  return cached || fetchPromise;
}

// Background sync for offline actions (future: queue mutations)
self.addEventListener('sync', event => {
  if (event.tag === 'nutrios-sync') {
    event.waitUntil(syncPendingActions());
  }
});

async function syncPendingActions() {
  // Placeholder: implementar fila de ações offline (check-ins, relatos, etc.)
  console.log('[SW] Background sync triggered');
}

// Push notifications (requires VAPID keys configured server-side)
self.addEventListener('push', event => {
  if (!event.data) return;
  const data = event.data.json();
  const options = {
    body: data.body || 'Nova atualização no NutriOS',
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    vibrate: [100, 50, 100],
    data: { url: data.url || '/app' },
    actions: [
      { action: 'open', title: 'Abrir' },
      { action: 'dismiss', title: 'Dispensar' }
    ],
    requireInteraction: true
  };
  event.waitUntil(self.registration.showNotification(data.title || 'NutriOS', options));
});

self.addEventListener('notificationclick', event => {
  event.notification.close();
  if (event.action === 'dismiss') return;
  const url = event.notification.data?.url || '/app';
  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(clientList => {
      for (const client of clientList) {
        if (client.url.includes(url) && 'focus' in client) return client.focus();
      }
      return clients.openWindow(url);
    })
  );
});