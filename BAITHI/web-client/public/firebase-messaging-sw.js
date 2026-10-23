importScripts('https://www.gstatic.com/firebasejs/12.19.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging-compat.js');

const firebaseConfig = {
  apiKey: 'AIzaSyD4qCOfTZKQC35UukZFcTbwrXtUEv84GU4',
  authDomain: 'file-85963.firebaseapp.com',
  projectId: 'file-85963',
  storageBucket: 'file-85963.firebasestorage.app',
  messagingSenderId: '569200800640',
  appId: '1:569200800640:web:eb5808c9ac673752cb8765',
};

firebase.initializeApp(firebaseConfig);
const messaging = firebase.messaging();

messaging.onBackgroundMessage((payload) => {
  if (payload && payload.notification) return;
  const title = (payload.data && payload.data.title) || 'StudySync';
  self.registration.showNotification(title, {
    body: (payload.data && payload.data.body) || '',
    icon: '/static/studysync-icon-v2-192.png',
    badge: '/static/studysync-icon-v2-72.png',
    tag: (payload.data && payload.data.tag) || 'studysync',
    renotify: false,
    data: { url: (payload.data && payload.data.url) || '/student' },
  });
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = new URL(event.notification.data?.url || '/student', self.location.origin).href;
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const client of windows) {
      if (client.url.startsWith(self.location.origin) && 'focus' in client) {
        await client.navigate(targetUrl);
        return client.focus();
      }
    }
    return self.clients.openWindow(targetUrl);
  })());
});
