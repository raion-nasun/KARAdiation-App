const CACHE = '{{CACHE_VERSION}}';
const SHELL = ['/', '/static/style.css', '/static/app.js',
  '/static/manifest.json', '/static/images/KARA 로고_로고만.png',
  '/static/images/KARA 로고_한글 포함.png'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() =>
        // 구버전 캐시 삭제 후 열린 탭 전체 새로고침 → 최신 버전 즉시 반영
        self.clients.matchAll({ type: 'window' }).then(clients =>
          clients.forEach(c => c.navigate(c.url))
        )
      )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (url.pathname.startsWith('/api/')) return;
  e.respondWith(
    caches.match(e.request).then(cached => {
      const net = fetch(e.request).then(res => {
        if (res.ok) caches.open(CACHE).then(c => c.put(e.request, res.clone()));
        return res;
      }).catch(() => cached);
      return cached || net;
    })
  );
});
