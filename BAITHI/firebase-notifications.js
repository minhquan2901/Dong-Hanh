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

async function registerWebToken(username, token) {
  const response = await fetch("/api/push/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, token }),
  });

  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw new Error(result.detail || `Backend đăng ký token thất bại: HTTP ${response.status}`);
  }
  return response.json();
}

export function isDesktopBrowser() {
  return !/Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
}

export async function enableWebNotifications(username) {
  if (!isDesktopBrowser()) {
    throw new Error("Thông báo đẩy hiện chỉ bật trên máy tính.");
  }
  if (!username) {
    throw new Error("Không xác định được tài khoản đang đăng nhập.");
  }

  const configResponse = await fetch("/api/push/config", { cache: "no-store" });
  const pushConfig = await configResponse.json();
  if (!configResponse.ok || !pushConfig.ready || !pushConfig.vapid_key) {
    throw new Error("Máy chủ chưa cấu hình Firebase FCM và VAPID key.");
  }

  await requestNotificationPermission();
  const serviceWorkerRegistration = await registerServiceWorker();
  await initializeMessaging();

  const token = await getToken(messaging, {
    vapidKey: pushConfig.vapid_key,
    serviceWorkerRegistration,
  });

  if (!token) {
    throw new Error("Firebase không tạo được web FCM token.");
  }

  await registerWebToken(username, token);
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

export { app, firebaseConfig };
