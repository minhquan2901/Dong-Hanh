importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging-compat.js');

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
    };
    self.registration.showNotification(title, options);
  });
}
