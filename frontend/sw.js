const CACHE_NAME = 'ainews-shell-v1';
const STATIC_ASSETS = [
  '/',
  '/static/index.html',
  '/static/css/base.css',
  '/static/css/article_card.css',
  '/static/css/footer.css',
  '/static/css/forms.css',
  '/static/css/header.css',
  '/static/css/layout.css',
  '/static/css/modals.css',
  '/static/css/navigation.css',
  '/static/css/responsive.css',
  '/static/css/search.css',
  '/static/css/setup_page.css',
  '/static/css/loading.css',
  '/static/favicon.svg',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Pre-caching shell assets');
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  clients.claim();
});

self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (request.method !== 'GET') {
    return;
  }

  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request).catch(() => {
        return new Response(
          JSON.stringify({ error: 'Offline - API not available' }),
          {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          }
        );
      })
    );
    return;
  }

  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.open(CACHE_NAME).then((cache) => {
        return cache.match(request).then((cachedResponse) => {
          const networkFetch = fetch(request).then((networkResponse) => {
            if (networkResponse.ok) {
              cache.put(request, networkResponse.clone());
            }
            return networkResponse;
          }).catch(() => null);

          return cachedResponse || networkFetch;
        });
      })
    );
    return;
  }

  if (url.pathname === '/') {
    event.respondWith(
      fetch(request).catch(() => caches.match('/'))
    );
    return;
  }

  event.respondWith(
    fetch(request).catch(() => caches.match('/'))
  );
});