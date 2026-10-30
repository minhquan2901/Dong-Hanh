import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, clearApiCache } from "./api";
import StudyCompanionDemo from "./StudyCompanionDemo";
import materialCatalog from "./materialCatalog.json";
import "./styles.css";

const USER_KEY = "study_sync_user";
const TOKEN_KEY = "study_sync_session_token";
const APP_CREDIT = "Made by ChiThien (8/1) và MinhQuan (8/2)";
const SCHEDULE_CACHE_PREFIX = "study_sync_schedule_cache_v1:";

function scheduleCacheKey(username) {
  return `${SCHEDULE_CACHE_PREFIX}${encodeURIComponent(String(username).trim().toLowerCase())}`;
}

function readScheduleCache(username) {
  try {
    const cached = localStorage.getItem(scheduleCacheKey(username));
    if (cached === null) return { slots: [], hasCache: false, error: "" };
    const slots = JSON.parse(cached);
    if (!Array.isArray(slots) || slots.some((slot) => !slot || typeof slot !== "object")) {
      throw new Error("Dữ liệu lịch đã lưu không đúng định dạng.");
    }
    return { slots, hasCache: true, error: "" };
  } catch (error) {
    return {
      slots: [],
      hasCache: false,
      error: `Không đọc được lịch đã lưu trên thiết bị: ${error.message}`,
    };
  }
}

function writeScheduleCache(username, slots) {
  const cachedSlots = slots.map(({ id, session, day, period, subject, lecturer }) => ({
    id,
    session,
    day,
    period,
    subject,
    lecturer,
  }));
  localStorage.setItem(scheduleCacheKey(username), JSON.stringify(cachedSlots));
}

function readSession() {
  try {
    const user = JSON.parse(localStorage.getItem(USER_KEY) || "null");
    const token = localStorage.getItem(TOKEN_KEY);
    return user && token ? { user, token } : null;
  } catch {
    return null;
  }
}

function App() {
  const [session, setSession] = useState(readSession);
  const [mode, setMode] = useState("login");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if ("serviceWorker" in navigator && window.isSecureContext) {
      navigator.serviceWorker.register("/firebase-messaging-sw.js").catch((error) => {
        console.error("Không đăng ký được service worker StudySync:", error);
      });
    }
    const clear = () => {
      clearApiCache();
      localStorage.removeItem(USER_KEY);
      localStorage.removeItem(TOKEN_KEY);
      setSession(null);
      setNotice("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
    };

    const renameUser = async (user) => {
      let suggestions = [];
      try {
        const result = await ownerApi(`/api/owner/username-bot/suggestions/${encodeURIComponent(user.username)}`, { method: "POST" });
        suggestions = result.suggestions || [];
      } catch (suggestionError) {
        setError(suggestionError.message);
        return;
      }
      const nextUsername = window.prompt(
        `Tên đăng nhập mới cho @${user.username}${suggestions.length ? ` (gợi ý: ${suggestions.join(", ")})` : ""}:`,
        suggestions[0] || user.username,
      );
      if (nextUsername === null || !nextUsername.trim() || nextUsername.trim() === user.username) return;
      if (!window.confirm(`Đổi @${user.username} thành @${nextUsername.trim()}? Người dùng sẽ cần đăng nhập lại bằng username mới.`)) return;
      setError("");
      try {
        await ownerApi(`/api/owner/users/${encodeURIComponent(user.id)}/username`, {
          method: "PATCH",
          body: JSON.stringify({ new_username: nextUsername.trim() }),
        });
        await load();
      } catch (renameError) { setError(renameError.message); }
    };
    window.addEventListener("studysync-session-expired", clear);
    return () => window.removeEventListener("studysync-session-expired", clear);
  }, []);

  const signOut = useCallback(() => {
    clearApiCache();
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(TOKEN_KEY);
    setSession(null);
    setNotice("");
  }, []);

  const pathname = window.location.pathname.replace(/\/+$/, "") || "/";
  if (pathname === "/demo") return <StudyCompanionDemo />;
  if (pathname === "/owner") {
    return <div className="app-shell"><header className="topbar"><a className="brand" href="/"><span className="brand-mark">S</span><span>StudySync</span></a></header><OwnerPortal /><footer className="footer">StudySync · Khu vực quản trị · {APP_CREDIT}</footer></div>;
  }

  const authenticate = async (payload, action) => {
    const result = await api(`/api/auth/${action}`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (action === "register") {
      setMode("login");
      setNotice(result.message || "Tạo tài khoản thành công. Hãy đăng nhập.");
      return;
    }
    if (result.requires_pin) return { requiresPin: true, message: result.message };
    localStorage.setItem(USER_KEY, JSON.stringify(result.user));
    localStorage.setItem(TOKEN_KEY, result.token);
    setSession({ user: result.user, token: result.token });
    setNotice("");
    return result;
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="StudySync trang chủ">
          <span className="brand-mark">S</span>
          <span className="brand-copy">Đồng hành<small>HỌC TẬP CÙNG BẠN</small></span>
        </a>
        <div className="topbar-right">
          <span className="connection"><i /> Học tập nhẹ nhàng hơn mỗi ngày</span>
          {session && <button className="button button-quiet" onClick={signOut}>Đăng xuất</button>}
        </div>
      </header>
      {session ? (
        <Dashboard session={session} onSignOut={signOut} pathname={pathname} />
      ) : (
        <AuthPanel
          mode={mode}
          setMode={setMode}
          authenticate={authenticate}
          notice={notice}
        />
      )}
      <footer className="footer">StudySync · Cùng xây dựng thói quen học tập tốt · {APP_CREDIT}</footer>
    </div>
  );
}

function AuthPanel({ mode, setMode, authenticate, notice }) {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [pinRequired, setPinRequired] = useState(false);
  const [role, setRole] = useState("student");

  const submit = async (event) => {
    event.preventDefault();
    setError("");
    setBusy(true);
    const values = new FormData(event.currentTarget);
    const payload = {
      username: String(values.get("username") || "").trim(),
      password: String(values.get("password") || ""),
      pin: String(values.get("pin") || ""),
      role,
      full_name: String(values.get("full_name") || "").trim(),
      class_name: String(values.get("class_name") || "").trim(),
    };
    try {
      const result = await authenticate(payload, mode === "login" ? "login" : "register");
      if (result?.requiresPin) setPinRequired(true);
      else setPinRequired(false);
    } catch (submitError) {
      setError(submitError.message);
    } finally {
      setBusy(false);
    }
  };

  const changeMode = (next) => {
    setMode(next);
    setPinRequired(false);
    setError("");
  };

  return (
    <main className="auth-layout">
      <section className="welcome-panel">
        <p className="eyebrow">KẾ HOẠCH HỌC TẬP, RÕ RÀNG HƠN</p>
        <h1>Tiến bộ mỗi ngày,<br /><span>cùng nhau đồng hành.</span></h1>
        <p className="welcome-copy">Lịch học, bài tập và tiến độ học tập được sắp xếp gọn gàng để học sinh chủ động hơn, phụ huynh an tâm hơn.</p>
        <div className="welcome-points">
          <div><span className="point-icon">✓</span><span>Theo dõi bài tập và hạn nộp</span></div>
          <div><span className="point-icon">◷</span><span>Nhìn rõ tiến độ học tập</span></div>
          <div><span className="point-icon">♡</span><span>Kết nối phụ huynh và học sinh</span></div>
        </div>
        <a className="demo-preview-link" href="/demo">Xem giao diện học sinh <span>→</span></a>
        <div className="welcome-art" aria-hidden="true"><span className="sun" /><span className="leaf leaf-one" /><span className="leaf leaf-two" /><span className="book">✦</span></div>
      </section>
      <section className="auth-card">
        <div className="auth-heading">
          <p className="eyebrow">CHÀO MỪNG BẠN</p>
          <h2>{mode === "login" ? "Đăng nhập" : "Tạo tài khoản"}</h2>
          <p>{mode === "login" ? "Tiếp tục hành trình học tập của bạn." : "Bắt đầu sử dụng StudySync miễn phí."}</p>
        </div>
        <div className="mode-switch" role="tablist" aria-label="Chế độ tài khoản">
          <button type="button" role="tab" aria-selected={mode === "login"} className={mode === "login" ? "selected" : ""} onClick={() => changeMode("login")}>Đăng nhập</button>
          <button type="button" role="tab" aria-selected={mode === "register"} className={mode === "register" ? "selected" : ""} onClick={() => changeMode("register")}>Đăng ký</button>
        </div>
        {(notice || error) && <div className={`message ${error ? "message-error" : "message-success"}`} role="status">{error || notice}</div>}
        <form className="auth-form" onSubmit={submit}>
          {mode === "register" && <>
            <label className="field">
              <span>Bạn là</span>
              <select value={role} onChange={(event) => setRole(event.target.value)}>
                <option value="student">Học sinh</option>
                <option value="parent">Phụ huynh</option>
              </select>
            </label>
            {(role === "student" || role === "parent") && <label className="field">
              <span>{role === "student" ? "Họ và tên" : "Tên phụ huynh"}</span>
              <input name="full_name" autoComplete="name" required placeholder="Ví dụ: Nguyễn Minh Anh" />
            </label>}
            {role === "student" && <label className="field">
              <span>Lớp</span>
              <input name="class_name" required placeholder="Ví dụ: 8/1" />
            </label>}
          </>}
          <label className="field">
            <span>Tên đăng nhập</span>
            <input name="username" autoComplete="username" minLength="6" maxLength="20" required placeholder="Nhập tên đăng nhập" />
          </label>
          <label className="field">
            <span>Mật khẩu</span>
            <input name="password" type="password" autoComplete={mode === "login" ? "current-password" : "new-password"} required placeholder="Nhập mật khẩu" />
          </label>
          {pinRequired && <label className="field">
            <span>Mã PIN đăng nhập</span>
            <input name="pin" inputMode="numeric" pattern="[0-9]{4,8}" minLength="4" maxLength="8" autoComplete="one-time-code" required autoFocus placeholder="Nhập mã PIN" />
          </label>}
          <button className="button button-primary submit-button" type="submit" disabled={busy}>
            {busy ? <span><span className="spinner" /> Đang xử lý...</span> : mode === "login" ? (pinRequired ? "Xác nhận PIN" : "Đăng nhập") : "Tạo tài khoản"}
          </button>
        </form>
        <p className="auth-hint">Bằng cách tiếp tục, bạn đồng ý sử dụng StudySync một cách an toàn và có trách nhiệm. <a href="/owner">Quản trị viên</a></p>
      </section>
    </main>
  );
}

function Dashboard({ session, onSignOut, pathname }) {
  const { user, token } = session;
  const [dashboard, setDashboard] = useState(null);
  const [scheduleSnapshot, setScheduleSnapshot] = useState(() => (
    user.role === "student" ? readScheduleCache(user.username) : { slots: [], hasCache: false, error: "" }
  ));
  const [scheduleCacheError, setScheduleCacheError] = useState(scheduleSnapshot.error);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);
  const [success, setSuccess] = useState("");
  const hasLoadedDashboard = useRef(false);

  const refresh = useCallback(async ({ forceRefresh = false } = {}) => {
    if (hasLoadedDashboard.current) setRefreshing(true);
    else setLoading(true);
    setError("");
    try {
      const path = user.role === "parent" ? "/api/dashboard/parent" : "/api/dashboard/student";
      const data = await api(`${path}?username=${encodeURIComponent(user.username)}`, { token, forceRefresh });
      setDashboard(data);
      hasLoadedDashboard.current = true;
      if (user.role === "student" && Array.isArray(data.schedule)) {
        setScheduleSnapshot({ slots: data.schedule, hasCache: true, error: "" });
        try {
          writeScheduleCache(user.username, data.schedule);
          setScheduleCacheError("");
        } catch (cacheError) {
          setScheduleCacheError(`Không lưu được bản thời khóa biểu trên thiết bị: ${cacheError.message}`);
        }
      }
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token, user.role, user.username]);

  useEffect(() => {
    if (
      pathname === "/account"
      || pathname === "/notifications"
      || pathname === "/student/schedule"
      || pathname === "/student/materials"
      || window.location.hash === "#schedule"
    ) return;
    refresh();
  }, [pathname, refresh, refreshKey]);

  const savedName = user.full_name || user.username;
  if (pathname === "/account") {
    return <AccountPage session={session} onSignOut={onSignOut} />;
  }
  if (pathname === "/student/schedule" || window.location.hash === "#schedule") {
    return user.role === "student"
      ? <SchedulePage session={session} />
      : <main className="dashboard"><div className="message message-error">Chỉ tài khoản học sinh mới có thời khóa biểu.</div></main>;
  }
  if (pathname === "/student/materials") {
    return user.role === "student"
      ? <StudentMaterialsPage />
      : <main className="dashboard"><div className="message message-error">Thư viện tài liệu dành cho học sinh.</div></main>;
  }
  if (pathname === "/student/tasks") {
    return user.role === "student"
      ? dashboard
        ? <StudentDashboard data={dashboard} user={user} token={token} onChanged={() => setRefreshKey((value) => value + 1)} onSuccess={setSuccess} success={success} taskPage />
        : error
          ? <main className="dashboard study-dashboard"><div className="message message-error dashboard-message" role="alert">{error}<button className="text-button" onClick={() => void refresh({ forceRefresh: true })}>Thử lại</button></div></main>
          : <main className="dashboard study-dashboard"><LoadingOverlay message="Đang tải nhiệm vụ..." /></main>
      : <main className="dashboard"><div className="message message-error">Chỉ tài khoản học sinh mới có trang nhiệm vụ.</div></main>;
  }
  if (pathname === "/notifications") {
    return <NotificationPage session={session} />;
  }

  return (
    <main className="dashboard study-dashboard">
      <section className="dashboard-hero">
        <div>
          <p className="eyebrow">{user.role === "parent" ? "GÓC ĐỒNG HÀNH" : "KHÔNG GIAN HỌC TẬP"}</p>
          <h1>Chào {savedName} <span className="wave">✦</span></h1>
          <p>{user.role === "parent" ? "Cùng theo dõi những bước tiến nhỏ mỗi ngày." : "Mỗi việc hoàn thành là một bước tiến mới."}</p>
        </div>
        <div className="hero-badge"><span>✧</span><div><strong>{new Date().toLocaleDateString("vi-VN", { weekday: "long" })}</strong><small>{new Date().toLocaleDateString("vi-VN", { day: "numeric", month: "long" })}</small></div></div>
      </section>
      <nav className="app-nav" aria-label="Điều hướng chính">
        <a className="active" href={user.role === "parent" ? "/parent" : "/student"}>Tổng quan</a>
        {user.role === "student" && <a href="/student/tasks">Nhiệm vụ</a>}
        {user.role === "student" && <a href="/student/materials">Tài liệu PDF</a>}
        {user.role === "student" && <a href="/student/schedule">Thời khóa biểu</a>}
        <a href="/notifications">Thông báo</a>
        <a href="/account">Tài khoản & bảo mật</a>
        <button className="nav-refresh" onClick={() => void refresh({ forceRefresh: true })} disabled={loading || refreshing}>{refreshing ? "Đang tải..." : "Làm mới"}</button>
      </nav>
      {error && <div className="message message-error dashboard-message" role="alert">{error}<button className="text-button" onClick={() => void refresh({ forceRefresh: true })}>Thử lại</button></div>}
      {scheduleCacheError && <div className="message message-error dashboard-message" role="alert">{scheduleCacheError}</div>}
      {success && <div className="message message-success dashboard-message" role="status">{success}<button className="message-close" onClick={() => setSuccess("")} aria-label="Đóng">×</button></div>}
      {loading && user.role === "student" && scheduleSnapshot.hasCache ? <>
        <CachedSchedulePanel slots={scheduleSnapshot.slots} />
        <LoadingState />
      </> : loading ? <LoadingOverlay message="Đang tải dữ liệu học tập..." /> : dashboard && user.role === "parent" ? (
        <ParentDashboard data={dashboard} user={user} token={token} />
      ) : dashboard ? (
        <StudentDashboard
          data={dashboard}
          user={user}
          token={token}
          onChanged={() => setRefreshKey((value) => value + 1)}
          onSuccess={setSuccess}
        />
      ) : null}
      {user.role === "parent" && <ParentProfiles user={user} token={token} onChanged={() => setRefreshKey((value) => value + 1)} />}
      <div className="legacy-callout"><div><strong>StudySync trên Vercel</strong><span>Giao diện được phục vụ từ Vercel; API và dữ liệu vẫn an toàn trên Render.</span></div><a className="button button-quiet" href="/account">Quản lý tài khoản</a></div>
    </main>
  );
}

function CachedSchedulePanel({ slots }) {
  return <section className="panel dashboard-schedule-grid">
    <div className="panel-heading"><div><p className="eyebrow">ĐANG ĐỒNG BỘ</p><h2>Thời khóa biểu đã lưu trên thiết bị</h2></div><span className="decor-icon">▦</span></div>
    <ScheduleGrid slots={slots} />
    <p className="section-help">Đây là bản xem gần nhất trên thiết bị. Lịch sẽ tự cập nhật khi máy chủ trả dữ liệu mới.</p>
  </section>;
}

function PageFrame({ title, eyebrow, children, backHref = "/", loading = false, loadingMessage }) {
  return <main className="dashboard">
    <div className="page-toolbar"><a className="button button-quiet" href={backHref}>← Tổng quan</a><span className="page-role">StudySync · Bảo mật dữ liệu</span></div>
    <section className="dashboard-hero page-hero"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div></section>
    <div className="page-stack">{children}</div>
    {loading && <LoadingOverlay message={loadingMessage} />}
  </main>;
}

function AccountPage({ session, onSignOut }) {
  const { user, token } = session;
  const [profile, setProfile] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [profileLoading, setProfileLoading] = useState(true);
  const [identityRequired, setIdentityRequired] = useState(
    localStorage.getItem("study_sync_identity_update_required") === "true",
  );
  const [pinEnabled, setPinEnabled] = useState(Boolean(user.pin_login_enabled));

  useEffect(() => {
    api(`/api/profile?username=${encodeURIComponent(user.username)}`, { token })
      .then(({ user: current }) => setProfile(current))
      .catch((loadError) => setError(loadError.message))
      .finally(() => setProfileLoading(false));
  }, [token, user.username]);

  const saveProfile = async (event) => {
    event.preventDefault();
    setMessage(""); setError("");
    const form = new FormData(event.currentTarget);
    try {
      const result = await api("/api/profile", {
        method: "PATCH", token,
        body: JSON.stringify({
          username: user.username,
          full_name: String(form.get("full_name")).trim(),
          class_name: String(form.get("class_name") || "").trim(),
          avatar: String(form.get("avatar") || "").trim(),
        }),
      });
      localStorage.setItem(USER_KEY, JSON.stringify(result.user));
      setProfile(result.user);
      setMessage("Đã lưu thông tin cá nhân.");
    } catch (saveError) { setError(saveError.message); }
  };

  const saveIdentity = async (event) => {
    event.preventDefault();
    setMessage(""); setError("");
    const form = new FormData(event.currentTarget);
    try {
      const result = await api("/api/profile/identity", {
        method: "POST", token,
        body: JSON.stringify({
          username: user.username,
          new_username: String(form.get("new_username")).trim(),
          full_name: String(form.get("full_name")).trim(),
          class_name: String(form.get("class_name") || "").trim(),
        }),
      });
      localStorage.setItem(USER_KEY, JSON.stringify(result.user));
      localStorage.setItem(TOKEN_KEY, result.token);
      localStorage.removeItem("study_sync_identity_update_required");
      setIdentityRequired(false);
      setMessage(result.message || "Đã cập nhật danh tính.");
      window.location.assign(user.role === "parent" ? "/parent" : "/student");
    } catch (saveError) { setError(saveError.message); }
  };

  const updatePassword = async (event) => {
    event.preventDefault();
    setMessage(""); setError("");
    const form = new FormData(event.currentTarget);
    const nextPassword = String(form.get("new_password"));
    if (nextPassword !== String(form.get("confirm_password"))) {
      setError("Mật khẩu nhập lại không khớp.");
      return;
    }
    try {
      const result = await api("/api/profile/password", {
        method: "POST", token,
        body: JSON.stringify({
          username: user.username,
          current_password: String(form.get("current_password")),
          new_password: nextPassword,
        }),
      });
      setMessage(result.message);
      window.setTimeout(onSignOut, 1200);
    } catch (passwordError) { setError(passwordError.message); }
  };

  const updatePin = async (event) => {
    event.preventDefault();
    setMessage(""); setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const pin = String(form.get("pin"));
    if (pin !== String(form.get("confirm_pin"))) {
      setError("Hai mã PIN chưa khớp.");
      return;
    }
    try {
      const result = await api("/api/security/pin", {
        method: "POST", token,
        body: JSON.stringify({ username: user.username, password: String(form.get("password")), pin }),
      });
      setMessage(result.message);
      formElement.reset();
    } catch (pinError) { setError(pinError.message); }
  };

  const updatePinLogin = async (event) => {
    event.preventDefault();
    setMessage(""); setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const enabled = !pinEnabled;
    try {
      const result = await api("/api/security/pin-login", {
        method: "POST", token,
        body: JSON.stringify({
          username: user.username, password: String(form.get("password")),
          enabled, pin: String(form.get("pin") || ""),
        }),
      });
      setPinEnabled(result.enabled);
      const nextUser = { ...user, pin_login_enabled: result.enabled };
      localStorage.setItem(USER_KEY, JSON.stringify(nextUser));
      setMessage(result.message);
      formElement.reset();
    } catch (pinError) { setError(pinError.message); }
  };

  const submitReport = async (event) => {
    event.preventDefault();
    setMessage(""); setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const result = await api("/api/reports", {
        method: "POST", token,
        body: JSON.stringify({
          username: user.username,
          category: String(form.get("category")),
          message: String(form.get("message")).trim(),
        }),
      });
      setMessage(result.message || "Đã gửi góp ý tới quản trị viên.");
      formElement.reset();
    } catch (reportError) { setError(reportError.message); }
  };

  return <PageFrame title="Tài khoản & bảo mật" eyebrow="THÔNG TIN CỦA BẠN" backHref={user.role === "parent" ? "/parent" : "/student"} loading={profileLoading} loadingMessage="Đang tải hồ sơ...">
    {(message || error) && <div className={`message ${error ? "message-error" : "message-success"}`} role={error ? "alert" : "status"}>{error || message}</div>}
    {identityRequired && <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">CẦN CẬP NHẬT</p><h2>Xác nhận danh tính tài khoản</h2></div></div>
      <p className="section-help">Cập nhật username và thông tin hồ sơ để tiếp tục sử dụng tài khoản.</p>
      <form className="settings-form" onSubmit={saveIdentity}>
        <Field label="Username mới" name="new_username" required minLength="6" maxLength="20" defaultValue={user.username} />
        <Field label="Họ và tên" name="full_name" required maxLength="100" defaultValue={profile?.full_name || user.full_name || ""} />
        {user.role === "student" && <Field label="Lớp" name="class_name" required defaultValue={profile?.class_name || user.class_name || ""} />}
        <button className="button button-primary">Cập nhật danh tính</button>
      </form>
    </section>}
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">HỒ SƠ</p><h2>Thông tin cá nhân</h2></div></div>
      {!profile && !error ? <LoadingState /> : <form className="settings-form" onSubmit={saveProfile}>
        <Field label="Tên đăng nhập" name="username" disabled value={profile?.username || user.username} />
        <Field label="Họ và tên" name="full_name" required maxLength="100" defaultValue={profile?.full_name || ""} />
        <Field label="Lớp" name="class_name" maxLength="50" defaultValue={profile?.class_name || ""} />
        <Field label="Avatar (chữ hoặc đường dẫn)" name="avatar" maxLength="100" defaultValue={profile?.avatar || ""} />
        <button className="button button-primary">Lưu thông tin</button>
      </form>}
    </section>
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">ĐĂNG NHẬP</p><h2>Đổi mật khẩu</h2></div></div>
      <form className="settings-form" onSubmit={updatePassword}>
        <Field label="Mật khẩu hiện tại" name="current_password" type="password" autoComplete="current-password" required />
        <Field label="Mật khẩu mới" name="new_password" type="password" autoComplete="new-password" minLength="6" required />
        <Field label="Nhập lại mật khẩu mới" name="confirm_password" type="password" autoComplete="new-password" minLength="6" required />
        <button className="button button-primary">Đổi mật khẩu</button>
      </form>
    </section>
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">BẢO MẬT THÊM</p><h2>Mã PIN đăng nhập</h2></div><span className="priority">{pinEnabled ? "Đang bật" : "Đang tắt"}</span></div>
      <form className="settings-form" onSubmit={updatePin}>
        <Field label="Mật khẩu hiện tại" name="password" type="password" autoComplete="current-password" required />
        <div className="form-row"><Field label="PIN mới (4–8 số)" name="pin" type="password" inputMode="numeric" pattern="[0-9]{4,8}" minLength="4" maxLength="8" required /><Field label="Nhập lại PIN" name="confirm_pin" type="password" inputMode="numeric" pattern="[0-9]{4,8}" minLength="4" maxLength="8" required /></div>
        <button className="button button-primary">Đăng ký PIN</button>
      </form>
      <form className="settings-form setting-divider" onSubmit={updatePinLogin}>
        <p className="section-help">Đăng nhập bằng PIN: {pinEnabled ? "đang yêu cầu PIN" : "chưa yêu cầu PIN"}.</p>
        <Field label="Mật khẩu hiện tại" name="password" type="password" autoComplete="current-password" required />
        {!pinEnabled && <Field label="PIN hiện tại để bật" name="pin" type="password" inputMode="numeric" pattern="[0-9]{4,8}" minLength="4" maxLength="8" required />}
        <button className="button button-quiet">{pinEnabled ? "Tắt yêu cầu PIN" : "Bật yêu cầu PIN"}</button>
      </form>
    </section>
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">PHẢN HỒI</p><h2>Báo lỗi hoặc góp ý</h2></div></div>
      <form className="settings-form" onSubmit={submitReport}>
        <label className="field"><span>Loại thông báo</span><select name="category"><option value="bug">Báo lỗi</option><option value="feedback">Góp ý</option></select></label>
        <label className="field"><span>Nội dung</span><textarea name="message" minLength="10" maxLength="2000" rows="4" required placeholder="Mô tả lỗi hoặc góp ý của bạn..." /></label>
        <button className="button button-primary">Gửi tới quản trị viên</button>
      </form>
    </section>
  </PageFrame>;
}

function Field({ label, ...props }) {
  return <label className="field"><span>{label}</span><input {...props} /></label>;
}

function SchedulePage({ session }) {
  const { user, token } = session;
  const imageInput = useRef(null);
  const [initialScheduleCache] = useState(() => readScheduleCache(user.username));
  const [slots, setSlots] = useState(initialScheduleCache.slots);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [cacheError, setCacheError] = useState(initialScheduleCache.error);
  const [preview, setPreview] = useState([]);
  const [pendingSlots, setPendingSlots] = useState([]);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(!initialScheduleCache.hasCache);
  const [refreshing, setRefreshing] = useState(initialScheduleCache.hasCache);
  const [isStale, setIsStale] = useState(initialScheduleCache.hasCache);
  const [loadFailed, setLoadFailed] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const hasScheduleSnapshot = useRef(initialScheduleCache.hasCache);

  const load = useCallback(async (forceRefresh = false) => {
    const showCachedSnapshot = hasScheduleSnapshot.current;
    setLoading(!showCachedSnapshot);
    setRefreshing(showCachedSnapshot);
    setIsStale(showCachedSnapshot);
    setLoadFailed(false);
    setError("");
    try {
      const result = await api(`/api/schedule/slots?username=${encodeURIComponent(user.username)}`, { token, forceRefresh });
      if (!Array.isArray(result.schedule)) {
        throw new Error("Máy chủ trả về thời khóa biểu không đúng định dạng. Vui lòng tải lại trang hoặc báo quản trị viên.");
      }
      const freshSlots = result.schedule.filter((slot) => slot && typeof slot === "object");
      setSlots(freshSlots);
      hasScheduleSnapshot.current = true;
      setIsStale(false);
      try {
        writeScheduleCache(user.username, freshSlots);
        setCacheError("");
      } catch (cacheWriteError) {
        setCacheError(`Không lưu được bản thời khóa biểu trên thiết bị: ${cacheWriteError.message}`);
      }
    } catch (loadError) {
      setLoadFailed(true);
      setError(showCachedSnapshot
        ? `Chưa đồng bộ được thời khóa biểu mới nhất. Đang hiện bản đã lưu: ${loadError.message}`
        : loadError.message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [token, user.username]);
  useEffect(() => {
    void load();
  }, [load]);

  const addSlot = async (event) => {
    event.preventDefault();
    const formElement = event.currentTarget.form;
    if (!formElement.reportValidity()) return;
    const form = new FormData(formElement);
    const duration = Number(form.get("duration"));
    const period = Number(form.get("period"));
    const subject = String(form.get("subject")).trim();
    if (!subject) return;
    if (period + duration - 1 > 7) {
      setError("Tiết đôi cần có tiết kế tiếp. Hãy chọn tiết bắt đầu từ 1 đến 6.");
      return;
    }
    setBusy(true);
    setError(""); setMessage("");
    const slotsToSave = Array.from({ length: duration }, (_, index) => ({
      id: `optimistic-${Date.now()}-${index}`,
      username: user.username,
      session: String(form.get("session")),
      day: String(form.get("day")),
      period: period + index,
      subject,
      lecturer: String(form.get("lecturer") || "").trim(),
    }));
    const previousSlots = slots;
    setSlots((current) => mergeScheduleSlots(current, slotsToSave));
    try {
      const result = await api("/api/schedule/slots", {
        method: "POST", token,
        body: JSON.stringify({ slots: slotsToSave }),
      });
      setMessage(result.message);
      setError("");
      formElement.elements.lecturer.value = "";
      formElement.elements.duration.value = "1";
      if (period + duration <= 7) formElement.elements.period.value = String(period + duration);
      await load(true);
    } catch (saveError) { setSlots(previousSlots); setError(saveError.message); }
    finally { setBusy(false); }
  };

  const queueSlot = (event) => {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const entry = {
      session: String(form.get("session")),
      day: String(form.get("day")),
      period: Number(form.get("period")),
      duration: Number(form.get("duration")),
      subject: String(form.get("subject")).trim(),
      lecturer: String(form.get("lecturer") || "").trim(),
    };
    if (!entry.subject) return;
    if (entry.period + entry.duration - 1 > 7) {
      setError("Tiết đôi cần có tiết kế tiếp. Hãy chọn tiết bắt đầu từ 1 đến 6.");
      return;
    }

    const occupiedPeriods = new Set(
      Array.from({ length: entry.duration }, (_, index) => entry.period + index),
    );
    setPendingSlots((current) => [
      ...current.filter((queued) => {
        if (queued.session !== entry.session || queued.day !== entry.day) return true;
        const queuedPeriods = Array.from(
          { length: queued.duration },
          (_, index) => queued.period + index,
        );
        return !queuedPeriods.some((period) => occupiedPeriods.has(period));
      }),
      entry,
    ]);
    setError("");
    setMessage("");
    formElement.elements.lecturer.value = "";
    formElement.elements.duration.value = "1";
    if (entry.period + entry.duration <= 7) {
      formElement.elements.period.value = String(entry.period + entry.duration);
    }
  };

  const savePendingSlots = async () => {
    if (!pendingSlots.length) {
      setMessage("Hãy thêm ít nhất một tiết vào danh sách chờ trước khi lưu.");
      setError("");
      return;
    }
    if (!window.confirm(`Bạn sắp lưu ${pendingSlots.length} mục thời khóa biểu:\n${pendingSlots.map((slot) => `${slot.subject} · ${slot.lecturer || "—"}`).join("\n")}\n\nTiếp tục lưu?`)) return;

    setBusy(true);
    setError("");
    setMessage("");
    const slotsToSave = pendingSlots.flatMap((entry, entryIndex) => Array.from({ length: entry.duration }, (_, index) => ({
      id: `optimistic-${Date.now()}-${entryIndex}-${index}`,
      username: user.username,
      session: entry.session,
      day: entry.day,
      period: entry.period + index,
      subject: entry.subject,
      lecturer: entry.lecturer,
    })));
    const previousSlots = slots;
    setSlots((current) => mergeScheduleSlots(current, slotsToSave));
    try {
      const result = await api("/api/schedule/slots", {
        method: "POST",
        token,
        body: JSON.stringify({ slots: slotsToSave }),
      });
      setMessage(result.message);
      setPendingSlots([]);
      await load(true);
    } catch (saveError) {
      setSlots(previousSlots);
      setError(saveError.message);
    } finally {
      setBusy(false);
    }
  };

  const removeSlot = async (slot) => {
    setBusy(true);
    setError(""); setMessage("");
    const previousSlots = slots;
    setSlots((current) => current.filter((item) => !sameScheduleSlot(item, slot)));
    try {
      const result = await api("/api/schedule/slot", {
        method: "DELETE", token,
        body: JSON.stringify({
          username: user.username, session: slot.session,
          day: String(slot.day), period: Number(slot.period),
        }),
      });
      setMessage(result.message);
      setError("");
      await load(true);
    } catch (removeError) { setSlots(previousSlots); setError(removeError.message); }
    finally { setBusy(false); }
  };

  const importImage = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true); setError(""); setMessage(""); setPreview([]);
    const body = new FormData();
    body.append("file", file);
    try {
      const imageStatus = await api("/api/schedule/import-image/status");
      if (!imageStatus.available) {
        throw new Error("Chức năng nhận diện ảnh chưa được bật trên máy chủ.");
      }
      const result = await api("/api/schedule/import-image", {
        method: "POST", token,
        headers: { "X-Username": user.username },
        body,
      });
      setPreview(result.slots || []);
      setMessage([result.message, ...(result.warnings || [])].join(" "));
    } catch (importError) { setError(importError.message); }
    finally { setBusy(false); }
  };

  const savePreview = async () => {
    setBusy(true); setError(""); setMessage("");
    const slotsToSave = preview.map((slot, index) => ({
      ...slot,
      id: `optimistic-${Date.now()}-${index}`,
      username: user.username,
    }));
    const previousSlots = slots;
    setSlots((current) => mergeScheduleSlots(current, slotsToSave));
    try {
      const result = await api("/api/schedule/slots", {
        method: "POST", token,
        body: JSON.stringify({ slots: slotsToSave }),
      });
      setMessage(result.message);
      setError("");
      setPreview([]);
      await load(true);
    } catch (saveError) { setSlots(previousSlots); setError(saveError.message); }
    finally { setBusy(false); }
  };

  return <PageFrame title="Thời khóa biểu" eyebrow="SẮP XẾP LỊCH HỌC" backHref="/student" loading={loading} loadingMessage="Đang tải thời khóa biểu...">
    {(error || message) && <div className={`message ${error ? "message-error" : "message-success"}`} role={error ? "alert" : "status"}>{error || message}{loadFailed && <button className="text-button" onClick={() => void load()}>Tải lại thời khóa biểu</button>}</div>}
    {cacheError && <div className="message message-error" role="alert">{cacheError}</div>}
    {refreshing && <p className="schedule-sync-status" role="status"><span className="spinner" /> Đang đồng bộ lịch mới nhất; bạn vẫn có thể xem lịch đã lưu.</p>}
    {isStale && loadFailed && <p className="section-help">Đang sử dụng bản lịch đã lưu trên thiết bị do chưa kết nối được máy chủ.</p>}
    <section className="schedule-editor-panel">
      <div className="schedule-editor-heading">
        <div><p className="eyebrow">QUẢN LÝ LỊCH HỌC</p><h2>{isEditing ? "Chỉnh sửa thời khóa biểu" : "Lịch học của bạn"}</h2><p>Thêm tiết thủ công hoặc nhập nhanh từ ảnh thời khóa biểu.</p></div>
        <div className="schedule-editor-actions">
          <button className={`button schedule-edit-button${isEditing ? " selected" : ""}`} type="button" onClick={() => setIsEditing(!isEditing)}><span aria-hidden="true">{isEditing ? "✓" : "✎"}</span>{isEditing ? "Xong chỉnh sửa" : "Chỉnh sửa thời khóa biểu"}</button>
          <button className="button schedule-ai-button" type="button" onClick={() => imageInput.current?.click()} disabled={busy}><span aria-hidden="true">✦</span>Tạo từ ảnh</button>
          <input ref={imageInput} className="schedule-hidden-file" type="file" accept="image/jpeg,image/png,image/webp" onChange={importImage} disabled={busy} aria-label="Chọn ảnh thời khóa biểu" />
        </div>
      </div>
      {isEditing && <div className="schedule-editor-body">
      <div className="panel-heading"><div><p className="eyebrow">THÊM TIẾT HỌC</p><h2>Nhập lịch học</h2></div></div>
      <form className="settings-form schedule-form" onSubmit={queueSlot}>
        <div className="form-row">
          <label className="field"><span>Buổi</span><select name="session"><option value="morning">Buổi sáng</option><option value="afternoon">Buổi chiều</option></select></label>
          <label className="field"><span>Thứ</span><select name="day">{["2", "3", "4", "5", "6", "7"].map((day) => <option key={day} value={day}>Thứ {day}</option>)}</select></label>
        </div>
        <div className="form-row">
          <label className="field"><span>Tiết</span><select name="period">{[1, 2, 3, 4, 5, 6, 7].map((period) => <option key={period}>{period}</option>)}</select></label>
          <label className="field"><span>Loại tiết</span><select name="duration"><option value="1">Tiết đơn</option><option value="2">Tiết đôi</option></select></label>
        </div>
        <div className="form-row">
          <Field label="Môn học" name="subject" required maxLength="100" />
          <Field label="Giáo viên (không bắt buộc)" name="lecturer" maxLength="100" />
        </div>
        <div className="toolbar-actions">
          <button className="button button-primary" type="submit" disabled={busy}>Thêm vào danh sách</button>
          <button className="button button-quiet" type="button" onClick={savePendingSlots} disabled={busy}>Lưu tất cả ({pendingSlots.length})</button>
          <button className="button button-quiet" type="button" onClick={() => setPendingSlots([])} disabled={busy || !pendingSlots.length}>Xóa danh sách</button>
          <button className="button button-quiet" type="button" onClick={addSlot} disabled={busy}>Lưu tiết học ngay</button>
        </div>
        {pendingSlots.length > 0 && <div className="schedule-queue" aria-live="polite">
          <strong>Danh sách chờ lưu ({pendingSlots.length})</strong>
          {pendingSlots.map((entry, index) => <div className="schedule-queue-item" key={`${entry.session}-${entry.day}-${entry.period}-${index}`}>
            <span>{entry.session === "morning" ? "Sáng" : "Chiều"}, thứ {entry.day}, {entry.duration === 2 ? `tiết ${entry.period}-${entry.period + 1} · tiết đôi` : `tiết ${entry.period} · tiết đơn`}: {entry.subject}{entry.lecturer ? ` · ${entry.lecturer}` : ""}</span>
            <button type="button" onClick={() => setPendingSlots((current) => current.filter((_, itemIndex) => itemIndex !== index))} aria-label={`Bỏ ${entry.subject} khỏi danh sách chờ`}>Bỏ</button>
          </div>)}
        </div>}
      </form>
      </div>}
    </section>
    {preview.length > 0 && <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">KIỂM TRA KẾT QUẢ AI</p><h2>Xem trước lịch nhận diện</h2></div><button className="button button-primary" onClick={savePreview} disabled={busy}>Lưu {preview.length} tiết</button></div>
      <p className="section-help">Hãy kiểm tra nội dung trước khi lưu. Kết quả AI có thể đọc nhầm ảnh.</p>
      <SlotList slots={preview} onRemove={(slot) => setPreview((items) => items.filter((item) => item !== slot))} />
    </section>}
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">LỊCH HIỆN TẠI</p><h2>{slots.length} tiết học</h2></div><button className="button button-quiet" onClick={() => void load(true)} disabled={busy || refreshing}>{refreshing ? "Đang tải..." : "Làm mới"}</button></div>
      {loadFailed && !hasScheduleSnapshot.current ? <EmptyState title="Chưa tải được thời khóa biểu" text="Danh sách chưa bị xóa. Kiểm tra kết nối rồi thử tải lại." /> : slots.length ? <ScheduleGrid slots={slots} onRemove={isEditing ? removeSlot : undefined} /> : <EmptyState title="Chưa có lịch học" text="Thêm tiết học bằng biểu mẫu hoặc nhận diện từ ảnh." />}
    </section>
  </PageFrame>;
}

function sameScheduleSlot(left, right) {
  return left.session === right.session
    && String(left.day) === String(right.day)
    && Number(left.period) === Number(right.period);
}

function mergeScheduleSlots(current, incoming) {
  const slotsByPosition = new Map(current.map((slot) => [
    `${slot.session}:${slot.day}:${slot.period}`,
    slot,
  ]));
  incoming.forEach((slot) => {
    slotsByPosition.set(`${slot.session}:${slot.day}:${slot.period}`, slot);
  });
  return Array.from(slotsByPosition.values());
}

function scheduleSubjectStyle(subject) {
  const name = String(subject || "").toLowerCase();
  if (name.includes("toán")) return { tone: "mint", icon: "∑" };
  if (name.includes("anh") || name.includes("ngoại ngữ")) return { tone: "blue", icon: "文" };
  if (name.includes("văn")) return { tone: "peach", icon: "文" };
  if (name.includes("lý")) return { tone: "lavender", icon: "⚛" };
  if (name.includes("hóa")) return { tone: "yellow", icon: "✳" };
  if (name.includes("sử") || name.includes("địa")) return { tone: "peach", icon: "◷" };
  if (name.includes("thể dục")) return { tone: "yellow", icon: "↗" };
  return { tone: "mint", icon: "✦" };
}

function ScheduleGrid({ slots, onRemove }) {
  const validSlots = slots.filter((slot) =>
    slot &&
    typeof slot === "object" &&
    ["2", "3", "4", "5", "6", "7"].includes(String(slot.day)) &&
    ["morning", "afternoon"].includes(slot.session) &&
    Number.isInteger(Number(slot.period)) &&
    Number(slot.period) >= 1 &&
    Number(slot.period) <= 7,
  );

  return <div className="schedule-grid-stack">
    {[
      ["morning", "Buổi sáng"],
      ["afternoon", "Buổi chiều"],
    ].map(([session, label]) => {
      const sessionSlots = validSlots.filter((slot) => slot.session === session);
      const periodCount = Math.max(5, ...sessionSlots.map((slot) => Number(slot.period)));
      return <div className="schedule-grid-section" key={session}>
        <h3>{label}</h3>
        <div className="schedule-table-scroll" role="region" aria-label={`Thời khóa biểu ${label.toLowerCase()}`} tabIndex="0">
          <table className="schedule-table">
            <thead><tr><th scope="col">Tiết</th>{["2", "3", "4", "5", "6", "7"].map((day) => <th scope="col" key={day}>Thứ {day}</th>)}</tr></thead>
            <tbody>{Array.from({ length: periodCount }, (_, index) => index + 1).map((period) => <tr key={period}>
              <th scope="row">{period}</th>
              {["2", "3", "4", "5", "6", "7"].map((day) => {
                const lessons = sessionSlots.filter((slot) => String(slot.day) === day && Number(slot.period) === period);
                return <td key={day}>{lessons.map((slot, index) => {
                  const subjectStyle = scheduleSubjectStyle(slot.subject);
                  return <article className={`schedule-cell-lesson tone-${subjectStyle.tone}`} key={`${slot.id || slot.subject}-${index}`}>
                  <span className="schedule-lesson-icon" aria-hidden="true">{subjectStyle.icon}</span>
                  <strong>{slot.subject || "Chưa có tên môn"}</strong>
                  {slot.lecturer && <small>{slot.lecturer}</small>}
                  {onRemove && <button className="button button-quiet button-small" onClick={() => onRemove(slot)} aria-label={`Xóa ${slot.subject || "tiết học"} thứ ${day}, tiết ${period}`}>Xóa</button>}
                </article>;
                })}</td>;
              })}
            </tr>)}</tbody>
          </table>
        </div>
      </div>;
    })}
    {slots.length > 0 && !validSlots.length && <EmptyState title="Chưa có tiết hợp lệ để hiển thị" text="Kiểm tra lại dữ liệu thời khóa biểu hoặc tải lại trang." />}
  </div>;
}

function SlotList({ slots, onRemove }) {
  return <div className="schedule-list">{slots.filter((slot) => slot && typeof slot === "object").map((slot, index) => <article className="schedule-row schedule-row-full" key={`${slot.day}-${slot.session}-${slot.period}-${index}`}>
    <span className="schedule-day">Thứ {slot.day}</span>
    <div className="task-main"><strong>{slot.subject}</strong><small>{slot.session === "morning" ? "Sáng" : "Chiều"} · Tiết {slot.period}{slot.lecturer ? ` · ${slot.lecturer}` : ""}</small></div>
    <button className="button button-quiet button-small" onClick={() => onRemove(slot)}>Xóa</button>
  </article>)}</div>;
}

function NotificationPage({ session }) {
  const { user, token } = session;
  const [prefs, setPrefs] = useState(null);
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);
  const [permission, setPermission] = useState("Notification" in window ? Notification.permission : "unsupported");

  const load = useCallback(async () => {
    setLoading(true);
    setLoadFailed(false);
    setError("");
    try {
      const [preferences, pushStatus] = await Promise.all([
        api(`/api/push/preferences?username=${encodeURIComponent(user.username)}`, { token }),
        api(`/api/push/status?username=${encodeURIComponent(user.username)}`, { token }),
      ]);
      setPrefs(preferences.reminders);
      setStatus(pushStatus);
    } catch (loadError) {
      setLoadFailed(true);
      setError(loadError.message);
    }
    finally { setLoading(false); }
  }, [token, user.username]);
  useEffect(() => { load(); }, [load]);

  const savePreferences = async (updates) => {
    setError(""); setMessage("");
    try {
      const result = await api("/api/push/preferences", {
        method: "POST", token,
        body: JSON.stringify({ username: user.username, ...updates }),
      });
      setPrefs(result.reminders);
      setMessage("Đã lưu cài đặt thông báo.");
    } catch (saveError) { setError(saveError.message); }
  };

  const enableNotifications = async () => {
    setBusy(true); setError(""); setMessage("");
    try {
      if (!("serviceWorker" in navigator) || !("Notification" in window)) {
        throw new Error("Trình duyệt này không hỗ trợ thông báo web.");
      }
      if (/iPhone|iPad|iPod/i.test(navigator.userAgent) && !window.matchMedia("(display-mode: standalone)").matches) {
        throw new Error("Trên iPhone/iPad, hãy thêm StudySync vào Màn hình chính rồi bật thông báo trong app.");
      }
      const permissionResult = await Notification.requestPermission();
      setPermission(permissionResult);
      if (permissionResult !== "granted") throw new Error("Bạn chưa cấp quyền thông báo cho trình duyệt.");
      const pushConfig = await api("/api/push/config");
      if (!pushConfig.ready || !pushConfig.vapid_key) throw new Error("Máy chủ chưa cấu hình Firebase FCM/VAPID.");
      const [{ initializeApp, getApps }, { getMessaging, getToken, isSupported }] = await Promise.all([
        import("https://www.gstatic.com/firebasejs/12.19.0/firebase-app.js"),
        import("https://www.gstatic.com/firebasejs/12.19.0/firebase-messaging.js"),
      ]);
      if (!(await isSupported())) throw new Error("Trình duyệt này chưa hỗ trợ Firebase Cloud Messaging.");
      const config = {
        apiKey: "AIzaSyD4qCOfTZKQC35UukZFcTbwrXtUEv84GU4",
        authDomain: "file-85963.firebaseapp.com",
        projectId: "file-85963",
        storageBucket: "file-85963.firebasestorage.app",
        messagingSenderId: "569200800640",
        appId: "1:569200800640:web:eb5808c9ac673752cb8765",
      };
      const firebaseApp = getApps().find((item) => item.name === "studysync-vercel") || initializeApp(config, "studysync-vercel");
      const registration = await navigator.serviceWorker.register("/firebase-messaging-sw.js");
      const messaging = getMessaging(firebaseApp);
      const fcmToken = await getToken(messaging, { vapidKey: pushConfig.vapid_key, serviceWorkerRegistration: registration });
      if (!fcmToken) throw new Error("Firebase không tạo được token thông báo.");
      const result = await api("/api/push/register", {
        method: "POST", token,
        body: JSON.stringify({ username: user.username, token: fcmToken }),
      });
      setMessage(result.message);
      await load();
    } catch (enableError) { setError(enableError.message); }
    finally { setBusy(false); }
  };

  const removeDevice = async (deviceId) => {
    setError(""); setMessage("");
    try {
      const result = await api("/api/push/devices/remove", {
        method: "POST", token,
        body: JSON.stringify({ username: user.username, device_id: deviceId }),
      });
      setMessage(result.message);
      await load();
    } catch (removeError) { setError(removeError.message); }
  };

  const testPush = async () => {
    setError(""); setMessage("");
    try {
      const result = await api("/api/push/test", {
        method: "POST", token,
        body: JSON.stringify({ username: user.username, device_id: "" }),
      });
      setMessage(result.message);
    } catch (testError) { setError(testError.message); }
  };

  const reminders = prefs || {};
  const quiet = reminders.quiet_hours || {};
  const milestones = reminders.deadline_milestones || [1440, 60, 10, 5];
  const toggle = (key, value) => setPrefs((current) => ({ ...current, [key]: value }));

  return <PageFrame title="Thông báo & nhắc việc" eyebrow="NHẮC ĐÚNG LÚC" backHref={user.role === "parent" ? "/parent" : "/student"} loading={loading} loadingMessage="Đang tải cài đặt thông báo...">
    {(error || message) && <div className={`message ${error ? "message-error" : "message-success"}`} role={error ? "alert" : "status"}>{error || message}{loadFailed && <button className="text-button" onClick={() => void load()}>Tải lại cài đặt</button>}</div>}
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">THIẾT BỊ NÀY</p><h2>Thông báo đẩy</h2></div><span className="priority">{permission === "granted" ? "Được cho phép" : permission === "denied" ? "Đang bị chặn" : "Chưa bật"}</span></div>
      <p className="section-help">Bật thông báo để nhận nhắc hạn và cập nhật trên thiết bị này. Trên iPhone/iPad cần mở StudySync từ Màn hình chính.</p>
      <div className="toolbar-actions"><button className="button button-primary" onClick={enableNotifications} disabled={busy}>{busy ? "Đang bật..." : "Bật thông báo trên thiết bị này"}</button><button className="button button-quiet" onClick={testPush}>Gửi thông báo thử</button></div>
      {!status?.ready && <p className="inline-error">Firebase push chưa sẵn sàng trên backend.</p>}
      <div className="device-list">{(status?.devices || []).map((device) => <div className="device-row" key={device.id}><span><strong>{device.label || (device.device_type === "mobile" ? "Điện thoại" : "Trình duyệt")}</strong><small>Hoạt động lần cuối: {device.last_seen_at || "chưa rõ"}</small></span><button className="button button-quiet button-small" onClick={() => removeDevice(device.id)}>Tắt thiết bị</button></div>)}</div>
    </section>
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">CÁ NHÂN HÓA</p><h2>Cài đặt nhắc nhở</h2></div></div>
      {!prefs ? loadFailed ? <EmptyState title="Chưa tải được cài đặt" text="Kiểm tra kết nối rồi thử tải lại." /> : <LoadingState /> : <>
        <div className="preference-list">
          {user.role === "student" && <label className="preference-row"><span><strong>Nhắc hạn bài tập</strong><small>Thông báo khi nhiệm vụ sắp đến hạn</small></span><input type="checkbox" checked={Boolean(reminders.deadline)} onChange={(event) => { toggle("deadline", event.target.checked); void savePreferences({ deadline: event.target.checked }); }} /></label>}
          {user.role === "student" && <label className="preference-row"><span><strong>Nhắc lịch học</strong><small>Nhắc trước giờ học theo thời khóa biểu</small></span><input type="checkbox" checked={Boolean(reminders.schedule)} onChange={(event) => { toggle("schedule", event.target.checked); void savePreferences({ schedule: event.target.checked }); }} /></label>}
          {user.role === "parent" && <label className="preference-row"><span><strong>Báo khi học sinh hoàn thành bài</strong><small>Nhận cập nhật từ học sinh đã liên kết</small></span><input type="checkbox" checked={Boolean(reminders.completion)} onChange={(event) => { toggle("completion", event.target.checked); void savePreferences({ completion: event.target.checked }); }} /></label>}
        </div>
        {user.role === "student" && <fieldset className="preference-group"><legend>Mốc nhắc hạn</legend><div className="milestone-list">{[[1440, "1 ngày"], [60, "1 giờ"], [10, "10 phút"], [5, "5 phút"]].map(([minutes, label]) => <label key={minutes}><input type="checkbox" checked={milestones.includes(minutes)} onChange={(event) => {
          const next = event.target.checked ? [...milestones, minutes] : milestones.filter((value) => value !== minutes);
          toggle("deadline_milestones", next);
          void savePreferences({ deadline_milestones: next });
        }} /> {label}</label>)}</div></fieldset>}
        <fieldset className="preference-group"><legend>Giờ yên lặng</legend>
          <div className="preference-row"><label><input type="checkbox" checked={Boolean(quiet.enabled)} onChange={(event) => {
            const next = { ...quiet, enabled: event.target.checked };
            toggle("quiet_hours", next); void savePreferences({ quiet_hours: next });
          }} /> Không nhắc trong khoảng giờ này</label></div>
          <div className="form-row"><label className="field"><span>Bắt đầu</span><input type="time" value={quiet.start || "22:00"} onChange={(event) => toggle("quiet_hours", { ...quiet, start: event.target.value })} onBlur={() => void savePreferences({ quiet_hours: reminders.quiet_hours })} /></label>
            <label className="field"><span>Kết thúc</span><input type="time" value={quiet.end || "07:00"} onChange={(event) => toggle("quiet_hours", { ...quiet, end: event.target.value })} onBlur={() => void savePreferences({ quiet_hours: reminders.quiet_hours })} /></label></div>
        </fieldset>
      </>}
    </section>
  </PageFrame>;
}

function ParentProfiles({ user, token, onChanged }) {
  const [students, setStudents] = useState([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const result = await api(`/api/parent/children?username=${encodeURIComponent(user.username)}`, { token });
      setStudents(result.students || []);
    } catch (loadError) { setError(loadError.message); }
  }, [token, user.username]);
  useEffect(() => { load(); }, [load]);

  const selected = students.find((student) => student.student_id === selectedId) || students[0];
  const saveStudent = async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(""); setMessage(""); setBusy(true);
    try {
      const result = await api("/api/parent/student", {
        method: "PATCH", token,
        body: JSON.stringify({
          parent_username: user.username,
          student_id: selected?.student_id || selectedId,
          full_name: String(form.get("full_name")).trim(),
          class_name: String(form.get("class_name") || "").trim(),
          avatar: String(form.get("avatar") || "").trim(),
          is_active: String(form.get("is_active")) === "true",
        }),
      });
      setMessage(result.message);
      await load();
      onChanged();
    } catch (saveError) { setError(saveError.message); }
    finally { setBusy(false); }
  };

  return <section className="panel parent-profiles">
    <div className="panel-heading"><div><p className="eyebrow">HỒ SƠ GIA ĐÌNH</p><h2>Quản lý học sinh đã liên kết</h2></div></div>
    {error && <p className="inline-error" role="alert">{error}</p>}
    {message && <p className="inline-success" role="status">{message}</p>}
    {students.length === 0 ? <EmptyState title="Chưa có học sinh liên kết" text="Gửi yêu cầu kết nối bằng mã học sinh ở dashboard." /> : <>
      <label className="field"><span>Chọn học sinh</span><select value={selectedId || students[0]?.student_id || ""} onChange={(event) => setSelectedId(event.target.value)}>{students.map((student) => <option key={student.student_id} value={student.student_id}>{student.full_name} · {student.student_id}</option>)}</select></label>
      {selected && <form className="settings-form" onSubmit={saveStudent}>
        <Field label="Họ tên" name="full_name" required defaultValue={selected.full_name || ""} key={`${selected.student_id}-name`} />
        <div className="form-row"><Field label="Lớp" name="class_name" defaultValue={selected.class_name || ""} key={`${selected.student_id}-class`} /><Field label="Avatar" name="avatar" defaultValue={selected.avatar || ""} key={`${selected.student_id}-avatar`} /></div>
        <label className="field"><span>Trạng thái tài khoản</span><select name="is_active" defaultValue={String(selected.is_active !== false)}><option value="true">Đang hoạt động</option><option value="false">Tạm khóa</option></select></label>
        <button className="button button-primary" disabled={busy}>{busy ? "Đang lưu..." : "Lưu hồ sơ học sinh"}</button>
      </form>}
    </>}
  </section>;
}

const OWNER_TOKEN_KEY = "study_sync_owner_token";
const OWNER_NAME_KEY = "study_sync_owner_username";

function OwnerPortal() {
  const [ownerToken, setOwnerToken] = useState(localStorage.getItem(OWNER_TOKEN_KEY) || "");
  const [ownerName, setOwnerName] = useState(localStorage.getItem(OWNER_NAME_KEY) || "");
  const [overview, setOverview] = useState(null);
  const [users, setUsers] = useState([]);
  const [reports, setReports] = useState([]);
  const [bot, setBot] = useState(null);
  const [health, setHealth] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("all");
  const [tab, setTab] = useState("overview");

  const ownerApi = useCallback((path, options = {}) => api(path, { ...options, token: ownerToken }), [ownerToken]);
  const load = useCallback(async () => {
    if (!ownerToken) return;
    setBusy(true); setError("");
    try {
      const [summary, userResult, reportResult, botResult, healthResult] = await Promise.all([
        ownerApi("/api/owner/overview"),
        ownerApi("/api/owner/users"),
        ownerApi("/api/owner/reports"),
        ownerApi("/api/owner/username-bot"),
        api("/health/data"),
      ]);
      setOverview(summary);
      setUsers(userResult.users || []);
      setReports(reportResult.reports || []);
      setBot(botResult);
      setHealth(healthResult);
    } catch (loadError) {
      if (loadError.message.includes("Phiên owner")) {
        localStorage.removeItem(OWNER_TOKEN_KEY);
        localStorage.removeItem(OWNER_NAME_KEY);
        setOwnerToken("");
      }
      setError(loadError.message);
    } finally { setBusy(false); }
  }, [ownerApi, ownerToken]);

  useEffect(() => { void load(); }, [load]);

  const login = async (event) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setError(""); setBusy(true);
    try {
      const result = await api("/api/owner/login", {
        method: "POST",
        body: JSON.stringify({ username: String(form.get("username")).trim(), password: String(form.get("password")) }),
      });
      localStorage.setItem(OWNER_TOKEN_KEY, result.token);
      localStorage.setItem(OWNER_NAME_KEY, result.username);
      setOwnerName(result.username);
      setOwnerToken(result.token);
    } catch (loginError) { setError(loginError.message); }
    finally { setBusy(false); }
  };

  const logout = () => {
    localStorage.removeItem(OWNER_TOKEN_KEY);
    localStorage.removeItem(OWNER_NAME_KEY);
    setOwnerToken(""); setOwnerName(""); setOverview(null);
    setUsers([]); setReports([]); setBot(null);
  };

  const toggleUser = async (user) => {
    const action = user.is_active ? "khóa" : "mở khóa";
    if (!window.confirm(`Bạn muốn ${action} tài khoản @${user.username}?`)) return;
    setError("");
    try {
      await ownerApi(`/api/owner/users/${encodeURIComponent(user.id)}/status`, {
        method: "PATCH", body: JSON.stringify({ is_active: !user.is_active }),
      });
      await load();
    } catch (actionError) { setError(actionError.message); }
  };

  const deleteUser = async (user) => {
    if (!window.confirm(`Xóa tài khoản @${user.username} và dữ liệu học tập? Thao tác này không thể hoàn tác.`)) return;
    setError("");
    try {
      await ownerApi(`/api/owner/users/${encodeURIComponent(user.id)}`, { method: "DELETE" });
      await load();
    } catch (actionError) { setError(actionError.message); }
  };

  const editUser = async (user) => {
    const fullName = window.prompt(`Họ tên cho @${user.username}:`, user.full_name || "");
    if (fullName === null) return;
    const className = window.prompt("Lớp (để trống nếu không có):", user.class_name || "");
    if (className === null) return;
    setError("");
    try {
      await ownerApi(`/api/owner/users/${encodeURIComponent(user.id)}`, {
        method: "PATCH",
        body: JSON.stringify({ full_name: fullName.trim(), class_name: className.trim() }),
      });
      await load();
    } catch (actionError) { setError(actionError.message); }
  };

  const markReport = async (report) => {
    setError("");
    try {
      await ownerApi(`/api/owner/reports/${encodeURIComponent(report.id)}`, {
        method: "PATCH", body: JSON.stringify({ read: !report.read }),
      });
      await load();
    } catch (actionError) { setError(actionError.message); }
  };

  const toggleBot = async (enabled) => {
    setError("");
    try {
      const result = await ownerApi("/api/owner/username-bot", {
        method: "PATCH", body: JSON.stringify({ enabled }),
      });
      setBot(result);
    } catch (actionError) { setError(actionError.message); }
  };

  const scanBot = async () => {
    setError("");
    try {
      setBot(await ownerApi("/api/owner/username-bot/scan", { method: "POST" }));
    } catch (actionError) { setError(actionError.message); }
  };

  const reviewViolation = async (violation) => {
    setError("");
    try {
      setBot(await ownerApi(`/api/owner/username-bot/violations/${encodeURIComponent(violation.username)}/review`, { method: "POST" }));
    } catch (actionError) { setError(actionError.message); }
  };

  const visibleUsers = users.filter((user) => {
    const matchesRole = roleFilter === "all" || user.role === roleFilter;
    const terms = [user.username, user.full_name, user.student_id, user.class_name].join(" ").toLocaleLowerCase();
    return matchesRole && terms.includes(search.toLocaleLowerCase());
  });

  if (!ownerToken) return <main className="owner-auth">
    <section className="auth-card"><div className="auth-heading"><p className="eyebrow">KHU VỰC RIÊNG</p><h2>Đăng nhập quản trị</h2><p>Dành riêng cho owner của StudySync.</p></div>
      {error && <div className="message message-error" role="alert">{error}</div>}
      <form className="auth-form" onSubmit={login}>
        <Field label="Tên quản trị" name="username" autoComplete="username" required />
        <Field label="Mật khẩu" name="password" type="password" autoComplete="current-password" required />
        <button className="button button-primary submit-button" disabled={busy}>{busy ? "Đang xác thực..." : "Đăng nhập quản trị"}</button>
      </form>
      <p className="auth-hint">Thông tin owner được xác thực bởi backend Render.</p>
    </section>
  </main>;

  const pendingReports = reports.filter((report) => !report.read).length;
  return <main className="dashboard owner-dashboard">
    <section className="dashboard-hero">
      <div><p className="eyebrow">QUẢN TRỊ HỆ THỐNG</p><h1>Xin chào {ownerName}</h1><p>Thống kê tài khoản và hoạt động StudySync.</p></div>
      <button className="button button-quiet" onClick={logout}>Đăng xuất owner</button>
    </section>
    <nav className="app-nav" aria-label="Điều hướng quản trị">
      {[["overview", "Tổng quan"], ["users", "Tài khoản"], ["reports", `Góp ý (${pendingReports})`], ["settings", "Kiểm duyệt"]].map(([key, label]) => <button key={key} className={tab === key ? "active" : ""} onClick={() => setTab(key)}>{label}</button>)}
      <button className="nav-refresh" onClick={() => void load()} disabled={busy}>{busy ? "Đang tải..." : "Làm mới"}</button>
    </nav>
    {error && <div className="message message-error dashboard-message" role="alert">{error}</div>}
    {tab === "overview" && <OwnerOverview overview={overview} reports={reports} health={health} />}
    {tab === "users" && <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">QUẢN LÝ NGƯỜI DÙNG</p><h2>{visibleUsers.length} tài khoản</h2></div></div>
      <div className="user-filter"><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tìm tên, username, mã học sinh..." /><select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}><option value="all">Tất cả vai trò</option><option value="student">Học sinh</option><option value="parent">Phụ huynh</option></select></div>
      <div className="owner-user-list">{visibleUsers.map((user) => <article className="owner-user" key={user.id}>
        <div className="student-details"><strong>{user.full_name || user.username} <span className={`priority ${user.is_active ? "priority-done" : "priority-cao"}`}>{user.is_active ? "Đang hoạt động" : "Đã khóa"}</span></strong><span>@{user.username} · {user.role === "student" ? "Học sinh" : "Phụ huynh"} · {user.student_id || "—"} · {user.class_name || "Chưa có lớp"}</span><small>{user.successful_actions || 0} thao tác thành công{user.policy_violations?.length ? ` · ${user.policy_violations.join(", ")}` : ""}</small></div>
        <div className="toolbar-actions"><button className="button button-quiet button-small" onClick={() => void editUser(user)}>Sửa</button><button className="button button-quiet button-small" onClick={() => void renameUser(user)}>Đổi tên</button><button className="button button-quiet button-small" onClick={() => void toggleUser(user)}>{user.is_active ? "Khóa" : "Mở khóa"}</button><button className="button button-danger button-small" onClick={() => void deleteUser(user)}>Xóa</button></div>
      </article>)}</div>
    </section>}
    {tab === "reports" && <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">HÒM THƯ</p><h2>Báo lỗi & góp ý</h2></div><span className="priority">{pendingReports} chưa đọc</span></div>
      <div className="report-list">{reports.length ? reports.slice().reverse().map((report) => <article className={`report-card ${report.read ? "" : "report-unread"}`} key={report.id}><div className="report-card-head"><strong>{report.category === "bug" ? "Báo lỗi" : "Góp ý"} · @{report.username}</strong><small>{report.created_at}</small></div><p>{report.message}</p><button className="button button-quiet button-small" onClick={() => void markReport(report)}>{report.read ? "Đánh dấu chưa đọc" : "Đánh dấu đã đọc"}</button></article>) : <EmptyState title="Hòm thư đang trống" text="Báo lỗi và góp ý mới sẽ hiển thị tại đây." />}</div>
    </section>}
    {tab === "settings" && <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">KIỂM DUYỆT TÀI KHOẢN</p><h2>Username và lớp</h2></div><span className="priority">{bot?.violation_count || 0} cảnh báo</span></div>
      <label className="preference-row"><span><strong>Bật bot kiểm duyệt</strong><small>Quét username/lớp khi đăng ký, đăng nhập và theo lịch.</small></span><input type="checkbox" checked={Boolean(bot?.enabled)} onChange={(event) => void toggleBot(event.target.checked)} /></label>
      <div className="toolbar-actions setting-actions"><button className="button button-primary" onClick={scanBot}>Quét ngay</button><span className="section-help">Lần quét gần nhất: {bot?.last_scan_at || "chưa có"}</span></div>
      {(bot?.violations || []).filter((item) => item.status === "pending").map((violation) => <article className="report-card report-unread" key={`${violation.username}-${violation.first_seen_at}`}><div className="report-card-head"><strong>@{violation.username || "đăng ký mới"}</strong><small>{violation.last_seen_at || violation.first_seen_at || ""}</small></div><p>{(violation.reasons || []).join(" · ")}</p><button className="button button-quiet button-small" onClick={() => void reviewViolation(violation)}>Đánh dấu đã xem</button></article>)}
    </section>}
  </main>;
}

function OwnerOverview({ overview, reports, health }) {
  const users = overview?.users || {};
  const metrics = [
    ["Tài khoản", users.total || 0, "blue"],
    ["Học sinh", users.students || 0, "green"],
    ["Phụ huynh", users.parents || 0, "amber"],
    ["Đã dùng tính năng", users.used_features || 0, "violet"],
    ["Thao tác thành công", overview?.successful_actions || 0, "blue"],
    ["Góp ý chưa đọc", reports.filter((item) => !item.read).length, "amber"],
  ];
  return <>
    <section className="stats-grid owner-stats">{metrics.map(([label, value, tone]) => <StatCard key={label} label={label} value={value} icon="▤" tone={tone} />)}</section>
    <section className="content-grid">
      <div className="panel"><div className="panel-heading"><div><p className="eyebrow">SỬ DỤNG</p><h2>Tính năng đã dùng</h2></div></div>
        {Object.entries(overview?.feature_usage || {}).length ? Object.entries(overview.feature_usage).map(([feature, count]) => <div className="device-row" key={feature}><strong>{{ schedule: "Thời khóa biểu", assignments: "Bài tập", parent_link: "Liên kết phụ huynh" }[feature] || feature}</strong><span>{count}</span></div>) : <EmptyState title="Chưa có thống kê" text="Thống kê sẽ cập nhật khi người dùng thao tác." />}
      </div>
      <div className="panel"><div className="panel-heading"><div><p className="eyebrow">SỨC KHỎE HỆ THỐNG</p><h2>Kiểm tra dữ liệu</h2></div></div>
        <div className="system-facts"><div><span>Backend lưu trữ</span><strong>{health?.backend || "—"}</strong></div><div><span>Tài khoản ghi nhận</span><strong>{health?.user_count ?? "—"}</strong></div><div><span>Khóa phiên bảo mật</span><strong>{health?.has_session_secret ? "Đã cấu hình" : "Chưa cấu hình"}</strong></div></div>
      </div>
    </section>
  </>;
}

function LoadingState() {
  return <div className="loading-card" role="status"><span className="spinner" /> Đang tải dữ liệu học tập...</div>;
}

function LoadingOverlay({ message = "Đang tải dữ liệu..." }) {
  return <div className="loading-overlay" role="status" aria-live="polite">
    <div className="loading-overlay-card"><span className="spinner" /><strong>{message}</strong><small>Vui lòng đợi một chút, dữ liệu đang được đồng bộ.</small></div>
  </div>;
}

function StudentDashboard({ data, user, token, onChanged, onSuccess, success, taskPage = false }) {
  const stats = data.stats || {};
  const [tasks, setTasks] = useState(data.assignments || []);
  const [creating, setCreating] = useState(false);
  useEffect(() => setTasks(data.assignments || []), [data.assignments]);
  const pendingTasks = tasks.filter((task) => !task.completed);
  const completedTasks = tasks.length - pendingTasks.length;
  const completionRate = tasks.length
    ? Math.round((completedTasks / tasks.length) * 100)
    : Number(stats.completion_rate || 0);
  const [showCreate, setShowCreate] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [taskError, setTaskError] = useState("");
  const [deleteCandidate, setDeleteCandidate] = useState(null);
  const [taskFilter, setTaskFilter] = useState("all");

  const updateTask = async (task, action) => {
    setBusyId(String(task.id));
    setTaskError("");
    if (action === "delete") {
      setTasks((current) => current.map((item) => String(item.id) === String(task.id)
        ? { ...item, deleting: true }
        : item));
    } else {
      const completed = !task.completed;
      setTasks((current) => current.map((item) => String(item.id) === String(task.id)
        ? { ...item, completed }
        : item));
    }
    try {
      if (action === "delete") {
        await api(`/api/assignments/${encodeURIComponent(task.id)}?username=${encodeURIComponent(user.username)}`, { method: "DELETE", token });
        setTasks((current) => current.filter((item) => String(item.id) !== String(task.id)));
        onSuccess("Đã xóa nhiệm vụ.");
      } else {
        await api(`/api/assignments/${encodeURIComponent(task.id)}`, {
          method: "PATCH",
          token,
          body: JSON.stringify({ completed: !task.completed, username: user.username }),
        });
        onSuccess(task.completed ? "Đã chuyển nhiệm vụ về đang làm." : "Tuyệt vời! Nhiệm vụ đã hoàn thành.");
      }
      onChanged();
    } catch (error) {
      if (action === "delete") {
        setTasks((current) => current.map((item) => String(item.id) === String(task.id)
          ? { ...item, deleting: false }
          : item));
      } else {
        setTasks((current) => current.map((item) => String(item.id) === String(task.id)
          ? { ...item, completed: Boolean(task.completed) }
          : item));
      }
      setTaskError(error.message);
    } finally {
      setBusyId("");
    }
  };

  const createTask = async (event) => {
    event.preventDefault();
    setTaskError("");
    const form = event.currentTarget;
    const values = new FormData(form);
    const payload = {
      title: String(values.get("title")).trim(),
      subject: String(values.get("subject")).trim(),
      description: String(values.get("description") || "").trim(),
      due_date: String(values.get("due_date")),
      due_time: String(values.get("due_time") || "23:59"),
      priority: String(values.get("priority") || "Trung bình"),
      username: user.username,
    };
    const optimisticId = `optimistic-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const optimisticTask = { ...payload, id: optimisticId, completed: false, status: "pending" };
    setCreating(true);
    setTasks((current) => [...current, optimisticTask]);
    try {
      const result = await api("/api/assignments", { method: "POST", token, body: JSON.stringify(payload) });
      if (result.assignment) {
        setTasks((current) => current.map((task) => task.id === optimisticId ? result.assignment : task));
      }
      setShowCreate(false);
      form.reset();
      onSuccess("Đã thêm nhiệm vụ mới.");
      onChanged();
    } catch (error) {
      setTasks((current) => current.filter((task) => task.id !== optimisticId));
      setTaskError(error.message);
    } finally {
      setCreating(false);
    }
  };

  const localToday = new Date();
  localToday.setMinutes(localToday.getMinutes() - localToday.getTimezoneOffset());
  const today = localToday.toISOString().slice(0, 10);

  if (taskPage) {
    const visibleTasks = tasks.filter((task) => (
      taskFilter === "all"
      || (taskFilter === "pending" && !task.completed)
      || (taskFilter === "completed" && task.completed)
    ));
    return <main className="dashboard study-dashboard task-management-page">
      <div className="task-page-back"><a className="button button-quiet" href="/student">← Tổng quan</a><span>Đồng hành học tập cùng bạn</span></div>
      <section className="task-page-heading">
        <div><p className="eyebrow">MỖI VIỆC NHỎ, MỘT BƯỚC TIẾN</p><h1>Nhiệm vụ học tập <span>✦</span></h1><p>Ghi lại điều cần làm, rồi tự hào đánh dấu khi bạn hoàn thành.</p></div>
        <div className="task-page-count"><strong>{pendingTasks.length}</strong><span>việc đang chờ</span></div>
      </section>
      {success && <div className="message message-success task-page-message" role="status">{success}</div>}
      <form className="task-quick-add" onSubmit={createTask}>
        <label className="task-quick-title"><span className="task-add-mark">＋</span><input name="title" required maxLength="120" placeholder="Thêm nhiệm vụ học tập mới hôm nay..." aria-label="Tên nhiệm vụ mới" /></label>
        <div className="task-quick-options">
          <label className="task-quick-field"><span>Môn học</span><input name="subject" required maxLength="80" placeholder="Ví dụ: Toán" /></label>
          <label className="task-quick-field"><span>Hạn hoàn thành</span><input name="due_date" type="date" required min={today} defaultValue={today} /></label>
          <input type="hidden" name="priority" value="Trung bình" />
          <button className="button button-primary task-add-button" type="submit" disabled={creating}>{creating ? <><span className="spinner" /> Đang thêm</> : "Thêm nhiệm vụ"}</button>
        </div>
      </form>
      {taskError && <p className="inline-error task-page-error" role="alert">{taskError}</p>}
      <section className="task-summary-row" aria-label="Tổng quan nhiệm vụ">
        <article><span className="task-summary-dot pending" /><span>Đang chờ</span><strong>{pendingTasks.length}</strong></article>
        <article><span className="task-summary-dot done" /><span>Đã hoàn thành</span><strong>{completedTasks}</strong></article>
        <article><span className="task-summary-dot progress" /><span>Tiến độ</span><strong>{completionRate}%</strong></article>
      </section>
      <section className="task-list-panel">
        <div className="task-list-heading"><div><p className="eyebrow">KẾ HOẠCH CỦA BẠN</p><h2>Danh sách nhiệm vụ</h2></div>
          <div className="task-filter-tabs" role="group" aria-label="Lọc nhiệm vụ">
            {[["all", "Tất cả"], ["pending", "Đang làm"], ["completed", "Đã xong"]].map(([value, label]) => <button key={value} type="button" className={taskFilter === value ? "active" : ""} onClick={() => setTaskFilter(value)}>{label}</button>)}
          </div>
        </div>
        {visibleTasks.length ? <AssignmentList tasks={visibleTasks} busyId={busyId} onToggle={(task) => void updateTask(task, "toggle")} onDelete={setDeleteCandidate} /> : (
          <div className="task-empty-state"><span className="task-empty-art">✿</span><strong>{taskFilter === "completed" ? "Chưa có nhiệm vụ hoàn thành" : taskFilter === "pending" ? "Bạn đã hoàn thành mọi việc!" : "Hôm nay thật thoáng đãng"}</strong><p>{taskFilter === "pending" ? "Tuyệt vời! Bạn có thể thêm nhiệm vụ mới khi sẵn sàng." : "Thêm một nhiệm vụ nhỏ để bắt đầu kế hoạch học tập."}</p></div>
        )}
      </section>
      {deleteCandidate && <TaskDeleteDialog task={deleteCandidate} busy={busyId === String(deleteCandidate.id)} onCancel={() => setDeleteCandidate(null)} onConfirm={async () => { const task = deleteCandidate; setDeleteCandidate(null); await updateTask(task, "delete"); }} />}
    </main>;
  }

  return <>
    <section className="stats-grid">
      <StatCard label="Tổng nhiệm vụ" value={tasks.length} icon="▤" tone="blue" />
      <StatCard label="Đang chờ" value={pendingTasks.length} icon="◷" tone="amber" />
      <StatCard label="Đã hoàn thành" value={completedTasks} icon="✓" tone="green" />
      <StatCard label="Tiến độ" value={`${completionRate}%`} icon="↗" tone="violet" />
    </section>
    <section className="panel dashboard-schedule-grid">
      <div className="panel-heading"><div><p className="eyebrow">LỊCH CẢ TUẦN</p><h2>Thời khóa biểu</h2></div><span className="decor-icon">▦</span></div>
      <ScheduleGrid slots={data.schedule || []} />
    </section>
    <section className="content-grid">
      <div className="panel task-panel">
        <div className="panel-heading">
          <div><p className="eyebrow">TẬP TRUNG TỪNG BƯỚC</p><h2>Nhiệm vụ của bạn</h2></div>
          <button className="button button-primary" onClick={() => setShowCreate((value) => !value)}>{showCreate ? "Đóng" : "+ Thêm nhiệm vụ"}</button>
        </div>
        {showCreate && <form className="task-create" onSubmit={createTask}>
          <label className="field"><span>Tên nhiệm vụ</span><input name="title" required maxLength="120" placeholder="Ví dụ: Ôn tập chương 3" /></label>
          <div className="form-row">
            <label className="field"><span>Môn học</span><input name="subject" required maxLength="80" placeholder="Toán" /></label>
            <label className="field"><span>Độ ưu tiên</span><select name="priority"><option>Trung bình</option><option>Cao</option><option>Thấp</option></select></label>
          </div>
          <div className="form-row">
            <label className="field"><span>Hạn hoàn thành</span><input name="due_date" type="date" required min={today} /></label>
            <label className="field"><span>Giờ</span><input name="due_time" type="time" defaultValue="23:59" /></label>
          </div>
          <label className="field"><span>Ghi chú (không bắt buộc)</span><textarea name="description" rows="2" maxLength="500" placeholder="Thêm chi tiết để dễ nhớ..." /></label>
          <button className="button button-primary" type="submit" disabled={creating}>{creating ? "Đang lưu..." : "Lưu nhiệm vụ"}</button>
        </form>}
        {taskError && <p className="inline-error" role="alert">{taskError}</p>}
        {tasks.length ? <div className="task-list">
          <AssignmentList tasks={tasks} busyId={busyId} onToggle={(task) => void updateTask(task, "toggle")} onDelete={setDeleteCandidate} />
        </div> : <EmptyState title="Chưa có nhiệm vụ nào" text="Thêm một việc cần làm để bắt đầu theo dõi tiến độ." />}
      </div>
      <aside className="side-column">
        <SchedulePanel schedule={data.schedule || []} />
        <LinkRequests user={user} token={token} onChanged={onChanged} />
      </aside>
    </section>
    {deleteCandidate && <TaskDeleteDialog task={deleteCandidate} busy={busyId === String(deleteCandidate.id)} onCancel={() => setDeleteCandidate(null)} onConfirm={async () => { const task = deleteCandidate; setDeleteCandidate(null); await updateTask(task, "delete"); }} />}
  </>;
}

function AssignmentList({ tasks, busyId, onToggle, onDelete }) {
  return <div className="task-list assignment-card-list">
    {tasks.map((task) => <article className={`task-row assignment-card ${task.completed ? "is-complete" : ""} ${task.deleting ? "is-deleting" : ""}`} key={task.id}>
      <button className={`check-button ${task.completed ? "checked" : ""}`} aria-label={task.completed ? "Đánh dấu chưa hoàn thành" : "Đánh dấu hoàn thành"} disabled={busyId === String(task.id)} onClick={() => onToggle(task)}>{task.completed ? "✓" : ""}</button>
      <div className="task-main"><strong>{task.title}</strong><span>{task.due_date ? `Hạn ${task.due_date}${task.due_time ? ` · ${task.due_time}` : ""}` : "Chưa đặt hạn"}</span></div>
      <span className="task-subject-tag">{task.subject || "Chưa phân loại"}</span>
      <span className={`priority priority-${String(task.priority || "trung bình").toLowerCase().replace(/\s/g, "-")}`}>{task.completed ? "Hoàn thành" : task.priority || "Trung bình"}</span>
      <button className="task-delete-button" aria-label={`Xóa ${task.title}`} title="Xóa nhiệm vụ" disabled={busyId === String(task.id)} onClick={() => onDelete(task)}>
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2m3 0-1 14H6L5 6m4 4v6m6-6v6" /></svg>
      </button>
    </article>)}
  </div>;
}

function TaskDeleteDialog({ task, busy, onCancel, onConfirm }) {
  return <div className="task-delete-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onCancel(); }}>
    <section className="task-delete-dialog" role="alertdialog" aria-modal="true" aria-labelledby="task-delete-title" aria-describedby="task-delete-description">
      <span className="task-delete-warning" aria-hidden="true">!</span>
      <h2 id="task-delete-title">Xóa nhiệm vụ này?</h2>
      <p id="task-delete-description"><strong>{task.title}</strong> sẽ bị xóa khỏi danh sách của bạn. Thao tác này không thể hoàn tác.</p>
      <div><button type="button" className="button button-quiet" onClick={onCancel} disabled={busy}>Giữ lại</button><button type="button" className="button task-delete-confirm" onClick={onConfirm} disabled={busy}>{busy ? "Đang xóa..." : "Xóa nhiệm vụ"}</button></div>
    </section>
  </div>;
}

function StudentMaterialsPage() {
  const [subjectFilter, setSubjectFilter] = useState("all");
  const [gradeFilter, setGradeFilter] = useState("all");
  const [volumeFilter, setVolumeFilter] = useState("all");
  const materials = materialCatalog;
  const visibleMaterials = materials.filter((material) => (
    (subjectFilter === "all" || material.subject === subjectFilter)
    &&
    (gradeFilter === "all" || String(material.grade) === gradeFilter)
    && (volumeFilter === "all" || String(material.volume || "") === volumeFilter)
  ));

  return <main className="dashboard study-dashboard materials-page">
    <div className="materials-back"><a className="button button-quiet" href="/student">← Tổng quan</a><span>Đồng hành học tập cùng bạn</span></div>
    <section className="materials-page-heading">
      <div><p className="eyebrow">THƯ VIỆN HỌC TẬP</p><h1>Tài liệu học tập <span>✦</span></h1><p>Tìm sách theo môn, lớp và tập để học đúng phần bạn cần.</p></div>
      <span className="materials-total">{materials.length} tài liệu</span>
    </section>
    <div className="materials-source-note" role="note">Tài liệu được mở từ Google Drive để không làm nặng website. Bạn có thể thêm link chia sẻ Drive cho từng sách.</div>
    <section className="materials-library">
      <div className="materials-toolbar">
        <div><span className="eyebrow">SÁCH THAM KHẢO · LỚP 6–9</span><strong>{visibleMaterials.length} tài liệu phù hợp</strong></div>
        <div className="materials-filters">
          <label><span>Môn</span><select value={subjectFilter} onChange={(event) => setSubjectFilter(event.target.value)}><option value="all">Tất cả môn</option>{[...new Set(materials.map((material) => material.subject))].map((subject) => <option key={subject} value={subject}>{subject}</option>)}</select></label>
          <label><span>Lớp</span><select value={gradeFilter} onChange={(event) => setGradeFilter(event.target.value)}><option value="all">Tất cả lớp</option>{[6, 7, 8, 9].map((grade) => <option key={grade} value={grade}>Lớp {grade}</option>)}</select></label>
          <label><span>Tập</span><select value={volumeFilter} onChange={(event) => setVolumeFilter(event.target.value)}><option value="all">Tất cả tập</option><option value="1">Tập 1</option><option value="2">Tập 2</option><option value="">Không chia tập</option></select></label>
        </div>
      </div>
      {visibleMaterials.length ? <div className="materials-card-list">{visibleMaterials.map((material) => <article className="learning-material-card" key={material.id}>
        <span className="learning-material-pdf">PDF</span>
        <div className="learning-material-info"><strong>{material.title}</strong><span>{material.subject} <i>·</i> Lớp {material.grade}{material.volume ? ` · Tập ${material.volume}` : ""}</span><small>{material.sourceUrl ? "PDF trên Google Drive" : "Chưa thêm link Google Drive"}</small></div>
        {material.sourceUrl ? <a className="button button-primary" href={material.sourceUrl} target="_blank" rel="noreferrer">Mở trên Drive ↗</a> : <button className="button button-quiet" type="button" disabled title="Thêm link chia sẻ Google Drive cho tài liệu này">Chưa có link Drive</button>}
      </article>)}</div> : <div className="materials-empty"><span>▤</span><strong>Không tìm thấy tài liệu phù hợp</strong><p>Thử đổi bộ lọc môn, lớp hoặc tập nhé.</p></div>}
    </section>
  </main>;
}

function ParentDashboard({ data, user, token }) {
  const overview = data.overview || {};
  const students = data.students || [];
  const tasks = data.tasks || [];
  const [linkCode, setLinkCode] = useState("");
  const [linkMessage, setLinkMessage] = useState("");
  const [linkError, setLinkError] = useState("");
  const [linkBusy, setLinkBusy] = useState(false);

  const linkStudent = async (event) => {
    event.preventDefault();
    setLinkBusy(true);
    setLinkMessage("");
    setLinkError("");
    try {
      const result = await api("/api/parent/link-student", {
        method: "POST",
        token,
        body: JSON.stringify({ parent_username: user.username, student_id: linkCode.trim() }),
      });
      setLinkMessage(result.message || "Đã gửi yêu cầu liên kết.");
      setLinkCode("");
    } catch (error) {
      setLinkError(error.message);
    } finally {
      setLinkBusy(false);
    }
  };

  return <>
    <section className="stats-grid">
      <StatCard label="Học sinh liên kết" value={overview.total_students ?? students.length} icon="♧" tone="blue" />
      <StatCard label="Đang chờ" value={overview.pending_tasks ?? 0} icon="◷" tone="amber" />
      <StatCard label="Đã hoàn thành" value={overview.completed_tasks ?? 0} icon="✓" tone="green" />
      <StatCard label="Tiến độ chung" value={`${overview.completion_rate ?? 0}%`} icon="↗" tone="violet" />
    </section>
    <section className="content-grid parent-content">
      <div className="panel">
        <div className="panel-heading"><div><p className="eyebrow">CÙNG CON TIẾN BƯỚC</p><h2>Học sinh của bạn</h2></div></div>
        {students.length ? <div className="student-list">
          {students.map((student) => <article className="student-card" key={student.username}>
            <div className="student-avatar">{(student.full_name || student.username || "H").slice(0, 1).toUpperCase()}</div>
            <div className="student-details"><strong>{student.full_name || student.username}</strong><span>{student.class_name || "Chưa cập nhật lớp"} · @{student.username}</span>
              <div className="progress-track"><span style={{ width: `${Math.max(0, Math.min(100, student.completion_rate || 0))}%` }} /></div>
              <small>{student.completion_rate || 0}% hoàn thành · {student.pending_tasks || 0} việc đang chờ</small>
            </div>
          </article>)}
        </div> : <EmptyState title="Chưa liên kết học sinh" text="Dùng biểu mẫu kết nối bên dưới để gửi yêu cầu bằng mã học sinh." />}
      </div>
      <div className="panel">
        <div className="panel-heading"><div><p className="eyebrow">THEO DÕI NHẸ NHÀNG</p><h2>Việc cần quan tâm</h2></div></div>
        {data.alerts?.length ? <div className="alert-list">{data.alerts.map((alert, index) => <article className={`alert-item alert-${alert.level || "info"}`} key={`${alert.title}-${index}`}><strong>{alert.title}</strong><span>{alert.student ? `${alert.student} · ` : ""}{alert.message}</span></article>)}</div> : <EmptyState title="Mọi thứ đang ổn" text="Thông tin mới sẽ xuất hiện tại đây." />}
        <form className="link-form" onSubmit={linkStudent}>
          <label className="field"><span>Mã học sinh để kết nối</span><input value={linkCode} onChange={(event) => setLinkCode(event.target.value)} required placeholder="Ví dụ: HS-001" /></label>
          <button className="button button-primary" type="submit" disabled={linkBusy}>{linkBusy ? "Đang gửi..." : "Gửi yêu cầu kết nối"}</button>
          {linkMessage && <p className="inline-success" role="status">{linkMessage}</p>}
          {linkError && <p className="inline-error" role="alert">{linkError}</p>}
        </form>
      </div>
    </section>
    <section className="panel parent-task-panel">
      <div className="panel-heading"><div><p className="eyebrow">TỔNG QUAN GIA ĐÌNH</p><h2>Nhiệm vụ gần đây</h2></div></div>
      {tasks.length ? <div className="task-list">{tasks.slice(0, 8).map((task, index) => <article className="task-row" key={`${task.student_name}-${task.title}-${index}`}><span className={`status-dot ${task.completed ? "done" : ""}`} /><div className="task-main"><strong>{task.title}</strong><span>{task.student_name} · {task.subject} · Hạn {task.due_date}</span></div><span className={`priority ${task.completed ? "priority-done" : "priority-pending"}`}>{task.completed ? "Hoàn thành" : "Đang chờ"}</span></article>)}</div> : <EmptyState title="Chưa có nhiệm vụ" text="Nhiệm vụ của học sinh liên kết sẽ được tổng hợp ở đây." />}
    </section>
  </>;
}

function StatCard({ label, value, icon, tone }) {
  return <article className="stat-card"><span className={`stat-icon tone-${tone}`}>{icon}</span><div><span className="stat-label">{label}</span><strong className="stat-value">{value}</strong></div></article>;
}

function SchedulePanel({ schedule }) {
  return <section className="panel schedule-panel">
    <div className="panel-heading"><div><p className="eyebrow">LỊCH HỌC</p><h2>Thời khóa biểu</h2></div><span className="decor-icon">▦</span></div>
    {Array.isArray(schedule) && schedule.length ? <div className="schedule-list">{schedule.filter((lesson) => lesson && typeof lesson === "object").slice(0, 5).map((lesson, index) => <article className="schedule-row" key={`${lesson.day}-${lesson.period}-${index}`}><span className="schedule-day">Thứ {lesson.day}</span><div><strong>{lesson.subject}</strong><small>Tiết {lesson.period} · {lesson.session === "morning" ? "Buổi sáng" : "Buổi chiều"}</small></div></article>)}</div> : <EmptyState title="Chưa có lịch học" text="Lịch học sẽ xuất hiện tại đây sau khi được thêm vào tài khoản học sinh." />}
  </section>;
}

function LinkRequests({ user, token, onChanged }) {
  const [requests, setRequests] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try {
      const response = await api(`/api/student/link-requests?username=${encodeURIComponent(user.username)}`, { token });
      setRequests((response.requests || []).filter((request) => request.status === "pending"));
    } catch (loadError) {
      setError(loadError.message);
    }
  }, [token, user.username]);

  useEffect(() => { load(); }, [load]);
  if (!requests.length && !error) return null;

  const respond = async (requestId, accept) => {
    setBusy(requestId);
    setError("");
    try {
      await api("/api/student/link-requests/respond", {
        method: "POST",
        token,
        body: JSON.stringify({ student_username: user.username, request_id: requestId, accept }),
      });
      await load();
      onChanged();
    } catch (responseError) {
      setError(responseError.message);
    } finally {
      setBusy("");
    }
  };

  return <section className="panel link-panel">
    <div className="panel-heading"><div><p className="eyebrow">KẾT NỐI</p><h2>Yêu cầu phụ huynh</h2></div></div>
    {error && <p className="inline-error">{error}</p>}
    {requests.map((request) => <article className="link-request" key={request.id}>
      <span><strong>{request.parent_name || request.parent_username}</strong><small>muốn kết nối với bạn</small></span>
      <div className="request-actions"><button className="button button-primary button-small" disabled={busy === request.id} onClick={() => respond(request.id, true)}>Đồng ý</button><button className="button button-quiet button-small" disabled={busy === request.id} onClick={() => respond(request.id, false)}>Từ chối</button></div>
    </article>)}
  </section>;
}

function EmptyState({ title, text }) {
  return <div className="empty-state"><span>✧</span><strong>{title}</strong><p>{text}</p></div>;
}

createRoot(document.getElementById("root")).render(<React.StrictMode><App /></React.StrictMode>);
