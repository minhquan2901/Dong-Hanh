import { initializeApp } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js";
import { getAnalytics, isSupported as analyticsIsSupported } from "https://www.gstatic.com/firebasejs/12.19.0/firebase-analytics.js";
import {
  getMessaging,
  getToken,
  deleteToken,
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

  if (Notification.permission === "denied") {
    throw new Error(isIOS()
      ? "StudySync đang bị chặn thông báo trên iPhone. Vào Cài đặt → Thông báo → StudySync và bật Cho phép thông báo. Nếu chưa thấy StudySync, hãy mở lại app từ biểu tượng Màn hình chính rồi thử lại."
      : "Thông báo đang bị chặn. Hãy mở cài đặt quyền của trang web trong trình duyệt, cho phép Thông báo rồi tải lại trang.");
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
    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem('study_sync_session_token') || ''}` },
    body: JSON.stringify({ username, token }),
  });

  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    throw new Error(result.detail || `Backend đăng ký token thất bại: HTTP ${response.status}`);
  }
  return response.json();
}

async function unregisterWebToken(username) {
  const response = await fetch("/api/push/unregister", {
    method: "POST",
    headers: { "Content-Type": "application/json", "Authorization": `Bearer ${localStorage.getItem('study_sync_session_token') || ''}` },
    body: JSON.stringify({ username }),
  });
  return response.ok;
}

// Firebase Web SDK cap nhat token qua getToken khi mo lai app.

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

// App PWA thường bị cache boi Service Worker nen token da gui truoc do có the
// da het han. Khi nguoi dung mo lai app, ta gui lai token hien tai de chắc chắn
// may chu van nhan duoc thong bao.
export async function syncNotificationToken(username) {
  if (!username) return null;
  if (Notification.permission !== "granted") return null;
  if (!messaging) {
    await initializeMessaging();
  }
  const configResponse = await fetch("/api/push/config", { cache: "no-store" });
  const pushConfig = await configResponse.json();
  if (!configResponse.ok || !pushConfig.ready || !pushConfig.vapid_key) return null;

  const serviceWorkerRegistration = await registerServiceWorker();
  const token = await getToken(messaging, {
    vapidKey: pushConfig.vapid_key,
    serviceWorkerRegistration,
  });
  if (!token) return null;
  await registerWebToken(username, token);
  return token;
}

export async function disableWebNotifications(username) {
  await unregisterWebToken(username);
  if (messaging) {
    try {
      await deleteToken(messaging);
    } catch (error) {
      console.warn("Không xóa được FCM token cục bộ:", error);
    }
  }
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

