const CACHE = 'lighthouse-v1';

// On install: pre-cache the shell so the app opens offline immediately
self.addEventListener('install', e => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE).then(c =>
      c.addAll(['./index.html', './manifest.json', './lighthouse.png'])
        .catch(() => {}) // first deploy — index.html may not exist yet
    )
  );
});

// On activate: take control immediately, drop old caches
self.addEventListener('activate', e => {
  e.waitUntil(
    Promise.all([
      clients.claim(),
      caches.keys().then(keys =>
        Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
      ),
    ])
  );
});

// Network-first: always try to get the freshest digest; fall back to cache
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request)
      .then(res => {
        const clone = res.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
