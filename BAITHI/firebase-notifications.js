import { initializeApp } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";
import { getAnalytics, isSupported as analyticsIsSupported } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-analytics.js";
import {
  getMessaging,
  getToken,
  isSupported as messagingIsSupported,
  onMessage,
} from "https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging.js";

const firebaseConfig = {
  apiKey: "AIzaSyD4qCOfTZKQC35UukZFcTbwrXtUEv84GU4",
  authDomain: "file-85963.firebaseapp.com",
  projectId: "file-85963",
  storageBucket: "file-85963.firebasestorage.app",
  messagingSenderId: "569200800640",
  appId: "1:569200800640:web:eb5808c9ac673752cb8765",
  measurementId: "G-EMNVJ7WV74",
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
    if (isIOS()) {
      throw new Error("Thông báo trên iPhone cần iOS 16.4 trở lên, mở bằng Safari và cài StudySync vào Màn hình chính.");
    }
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

export function isIOS() {
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

// Thong bao duoi nen chi chay khi web da duoc cai dat nhu mot app (PWA).
// tren iOS chi Safari cho phep cai, va phai iOS 16.4 tro len.
export function isInstalledAsApp() {
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    window.navigator.standalone === true
  );
}

function describeMobileRequirement() {
  if (isIOS()) {
    return "Trên iPhone, hãy cập nhật iOS lên 16.4 trở lên, mở trang bằng Safari, bấm Chia sẻ → Thêm vào Màn hình chính rồi bật thông báo trong app vừa cài.";
  }
  return "Hãy cho phép thông báo trong trình duyệt. Nếu muốn cài StudySync như app, mở menu trình duyệt → Cài ứng dụng (Install app).";
}

export async function enableWebNotifications(username) {
  if (!username) {
    throw new Error("Không xác định được tài khoản đang đăng nhập.");
  }

  if (isIOS() && !isInstalledAsApp()) {
    throw new Error(describeMobileRequirement());
  }

  await requestNotificationPermission();

  const configResponse = await fetch("/api/push/config", { cache: "no-store" });
  const pushConfig = await configResponse.json();
  if (!configResponse.ok || !pushConfig.ready || !pushConfig.vapid_key) {
    throw new Error("Máy chủ chưa cấu hình Firebase FCM và VAPID key.");
  }

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
    icon: payload.notification?.icon || "/static/studysync-icon-v2-192.png",
    data: payload.data || {},
  });
}

export async function initializeFirebaseNotifications() {
  await initializeAnalytics();
  await initializeMessaging();
  return app;
}

export { app, firebaseConfig };

