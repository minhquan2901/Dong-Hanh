import { initializeApp } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";
import { getAnalytics, isSupported as analyticsIsSupported } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-analytics.js";
import {
  getMessaging,
  getToken,
  isSupported as messagingIsSupported,
  onMessage,
} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging.js";

const firebaseConfig = {
  apiKey: "AIzaSyA7uKlNdac6bKI2heRww1jUZieKNvw14lM",
  authDomain: "baithi-f2647.firebaseapp.com",
  projectId: "baithi-f2647",
  storageBucket: "baithi-f2647.firebasestorage.app",
  messagingSenderId: "170056821362",
  appId: "1:170056821362:web:094ebfa5d599dc2b0f30eb",
  measurementId: "G-30CJXLJR9W",
};

const BACKEND_URL = "http://localhost:8000";
const VAPID_KEY = "YOUR_FIREBASE_WEB_PUSH_CERTIFICATE_KEY_PAIR";
const SERVICE_WORKER_PATH = "/firebase-messaging-sw.js";

const app = initializeApp(firebaseConfig);
let messaging = null;

async function initializeAnalytics() {
  if (firebaseConfig.measurementId && await analyticsIsSupported()) {
    return getAnalytics(app);
  }
  return null;
}

async function initializeMessaging() {
  if (!await messagingIsSupported()) {
    throw new Error("Trình duyệt này không hỗ trợ Firebase Cloud Messaging.");
  }
  messaging = getMessaging(app);
  return messaging;
}

async function registerServiceWorker() {
  if (!("serviceWorker" in navigator)) {
    throw new Error("Trình duyệt này không hỗ trợ service worker.");
  }
  return navigator.serviceWorker.register(SERVICE_WORKER_PATH);
}

async function requestNotificationPermission() {
  if (!("Notification" in window)) {
    throw new Error("Trình duyệt này không hỗ trợ thông báo.");
  }

  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Bạn chưa cấp quyền thông báo cho trình duyệt.");
  }
  return permission;
}

async function registerWebToken(token) {
  const response = await fetch(`${BACKEND_URL}/device/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ token, device_type: "web" }),
  });

  if (!response.ok) {
    throw new Error(`Backend đăng ký token thất bại: HTTP ${response.status}`);
  }
  return response.json();
}

export async function enableWebNotifications() {
  if (VAPID_KEY.startsWith("YOUR_")) {
    throw new Error("Hãy thay VAPID_KEY bằng Web Push certificate key pair trong Firebase Console.");
  }

  await requestNotificationPermission();
  const serviceWorkerRegistration = await registerServiceWorker();
  await initializeMessaging();

  const token = await getToken(messaging, {
    vapidKey: VAPID_KEY,
    serviceWorkerRegistration,
  });

  if (!token) {
    throw new Error("Firebase không tạo được web FCM token.");
  }

  await registerWebToken(token);
  return token;
}

export function listenForForegroundMessages(showNotification = showBrowserNotification) {
  if (!messaging) {
    throw new Error("Hãy gọi enableWebNotifications() trước khi lắng nghe thông báo.");
  }
  return onMessage(messaging, (payload) => {
    const title = payload.notification?.title || "StudySync";
    const body = payload.notification?.body || "Bạn có thông báo mới.";
    showNotification(title, body, payload);
  });
}

export function showBrowserNotification(title, body, payload = {}) {
  if (Notification.permission !== "granted") {
    return null;
  }

  return new Notification(title, {
    body,
    icon: payload.notification?.icon || "/static/studysync-icon.svg",
    data: payload.data || {},
  });
}

export async function initializeFirebaseNotifications() {
  await initializeAnalytics();
  await initializeMessaging();
  return app;
}

export { app, firebaseConfig, BACKEND_URL };

// Optional convenience hook: add data-enable-web-notifications to any button.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-enable-web-notifications]");
  if (!button) {
    return;
  }

  button.disabled = true;
  try {
    await enableWebNotifications();
    button.dispatchEvent(new CustomEvent("web-notifications-enabled", { bubbles: true }));
  } catch (error) {
    console.error("Không thể bật Firebase Web Notification:", error);
    button.dispatchEvent(new CustomEvent("web-notifications-error", {
      bubbles: true,
      detail: error,
    }));
  } finally {
    button.disabled = false;
  }
});
