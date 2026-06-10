const CACHE_NAME = 'attendance-system-v1';
const STATIC_CACHE = 'attendance-static-v1';
const API_CACHE = 'attendance-api-v1';

// الملفات التي سيتم تخزينها مؤقتاً
const urlsToCache = [
  '/',
  '/static/manifest.json',
  '/static/icons/icon-72x72.png',
  '/static/icons/icon-96x96.png',
  '/static/icons/icon-128x128.png',
  '/static/icons/icon-144x144.png',
  '/static/icons/icon-152x152.png',
  '/static/icons/icon-192x192.png',
  '/static/icons/icon-384x384.png',
  '/static/icons/icon-512x512.png',
  '/offline'
];

// تثبيت Service Worker
self.addEventListener('install', event => {
  console.log('Service Worker installing...');
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then(cache => {
        console.log('Caching static assets');
        return cache.addAll(urlsToCache);
      })
      .then(() => self.skipWaiting())
  );
});

// تنشيط Service Worker
self.addEventListener('activate', event => {
  console.log('Service Worker activating...');
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheName !== STATIC_CACHE && cacheName !== API_CACHE) {
            console.log('Deleting old cache:', cacheName);
            return caches.delete(cacheName);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// معالجة الطلبات
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  
  // معالجة طلبات API
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(event.request)
        .then(response => {
          // تخزين استجابة API مؤقتاً
          const responseToCache = response.clone();
          caches.open(API_CACHE).then(cache => {
            cache.put(event.request, responseToCache);
          });
          return response;
        })
        .catch(() => {
          // إذا فشل الاتصال، جلب من التخزين المؤقت
          return caches.match(event.request)
            .then(cachedResponse => {
              if (cachedResponse) {
                return cachedResponse;
              }
              // إرجاع استجابة مخصصة للـ API في وضع عدم الاتصال
              return new Response(JSON.stringify({
                success: false,
                message: 'لا يوجد اتصال بالإنترنت. يرجى المحاولة لاحقاً.',
                offline: true
              }), {
                headers: { 'Content-Type': 'application/json' }
              });
            });
        })
    );
    return;
  }
  
  // معالجة الطلبات العادية (HTML, CSS, JS)
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }
        return fetch(event.request)
          .then(response => {
            // تخزين الملفات الثابتة فقط
            if (event.request.method === 'GET' && 
                (url.pathname.endsWith('.css') || 
                 url.pathname.endsWith('.js') || 
                 url.pathname.endsWith('.png') ||
                 url.pathname.endsWith('.jpg'))) {
              const responseToCache = response.clone();
              caches.open(STATIC_CACHE).then(cache => {
                cache.put(event.request, responseToCache);
              });
            }
            return response;
          })
          .catch(() => {
            // صفحة عدم الاتصال
            if (event.request.mode === 'navigate') {
              return caches.match('/offline');
            }
            return new Response('محتويات غير متاحة حالياً', {
              status: 503,
              headers: { 'Content-Type': 'text/plain' }
            });
          });
      })
  );
});

// دفع الإشعارات (اختياري)
self.addEventListener('push', event => {
  const data = event.data.json();
  const options = {
    body: data.body,
    icon: '/static/icons/icon-192x192.png',
    badge: '/static/icons/icon-72x72.png',
    vibrate: [200, 100, 200],
    data: {
      url: data.url || '/'
    }
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// التعامل مع النقر على الإشعار
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(
    clients.openWindow(event.notification.data.url)
  );
});