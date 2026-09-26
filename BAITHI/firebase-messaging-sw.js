importScripts('https://www.gstatic.com/firebasejs/12.19.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging-compat.js');

// Service workers run in the browser, so process.env is unavailable here.
// Keep the public Firebase web configuration in this file for background push.
const firebaseConfig = {
  apiKey: 'AIzaSyA7uKlNdac6bKI2heRww1jUZieKNvw14lM',
  authDomain: 'baithi-f2647.firebaseapp.com',
  projectId: 'baithi-f2647',
  storageBucket: 'baithi-f2647.firebasestorage.app',
  messagingSenderId: '170056821362',
  appId: '1:170056821362:web:094ebfa5d599dc2b0f30eb',
};

if (firebaseConfig.apiKey && firebaseConfig.projectId) {
  firebase.initializeApp(firebaseConfig);
  const messaging = firebase.messaging();

  messaging.onBackgroundMessage((payload) => {
    const title = payload.notification?.title || 'StudySync';
    const options = {
      body: payload.notification?.body || '',
      icon: '/static/studysync-icon.svg',
      badge: '/static/studysync-icon.svg',
      data: { url: payload.data?.url || payload.fcmOptions?.link || '/student' },
    };
    self.registration.showNotification(title, options);
  });
}

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
