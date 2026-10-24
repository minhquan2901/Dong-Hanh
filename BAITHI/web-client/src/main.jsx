import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { api } from "./api";
import "./styles.css";

const USER_KEY = "study_sync_user";
const TOKEN_KEY = "study_sync_session_token";
const APP_CREDIT = "Made by ChiThien (8/1) và MinhQuan (8/2)";

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
    localStorage.removeItem(USER_KEY);
    localStorage.removeItem(TOKEN_KEY);
    setSession(null);
    setNotice("");
  }, []);

  const pathname = window.location.pathname.replace(/\/+$/, "") || "/";
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
          <span>StudySync</span>
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
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);
  const [success, setSuccess] = useState("");

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const path = user.role === "parent" ? "/api/dashboard/parent" : "/api/dashboard/student";
      const data = await api(`${path}?username=${encodeURIComponent(user.username)}`, { token });
      setDashboard(data);
    } catch (loadError) {
      setError(loadError.message);
    } finally {
      setLoading(false);
    }
  }, [token, user.role, user.username]);

  useEffect(() => { refresh(); }, [refresh, refreshKey]);

  const savedName = user.full_name || user.username;
  if (pathname === "/account") {
    return <AccountPage session={session} onSignOut={onSignOut} />;
  }
  if (pathname === "/student/schedule" || window.location.hash === "#schedule") {
    return user.role === "student"
      ? <SchedulePage session={session} />
      : <main className="dashboard"><div className="message message-error">Chỉ tài khoản học sinh mới có thời khóa biểu.</div></main>;
  }
  if (pathname === "/notifications") {
    return <NotificationPage session={session} />;
  }

  return (
    <main className="dashboard">
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
        {user.role === "student" && <a href="/student/schedule">Thời khóa biểu</a>}
        <a href="/notifications">Thông báo</a>
        <a href="/account">Tài khoản & bảo mật</a>
      </nav>
      {error && <div className="message message-error dashboard-message" role="alert">{error}<button className="text-button" onClick={() => setRefreshKey((value) => value + 1)}>Thử lại</button></div>}
      {success && <div className="message message-success dashboard-message" role="status">{success}<button className="message-close" onClick={() => setSuccess("")} aria-label="Đóng">×</button></div>}
      {loading ? <LoadingState /> : dashboard && user.role === "parent" ? (
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

function PageFrame({ title, eyebrow, children, backHref = "/" }) {
  return <main className="dashboard">
    <div className="page-toolbar"><a className="button button-quiet" href={backHref}>← Tổng quan</a><span className="page-role">StudySync · Bảo mật dữ liệu</span></div>
    <section className="dashboard-hero page-hero"><div><p className="eyebrow">{eyebrow}</p><h1>{title}</h1></div></section>
    <div className="page-stack">{children}</div>
  </main>;
}

function AccountPage({ session, onSignOut }) {
  const { user, token } = session;
  const [profile, setProfile] = useState(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [identityRequired, setIdentityRequired] = useState(
    localStorage.getItem("study_sync_identity_update_required") === "true",
  );
  const [pinEnabled, setPinEnabled] = useState(Boolean(user.pin_login_enabled));

  useEffect(() => {
    api(`/api/profile?username=${encodeURIComponent(user.username)}`, { token })
      .then(({ user: current }) => setProfile(current))
      .catch((loadError) => setError(loadError.message));
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

  return <PageFrame title="Tài khoản & bảo mật" eyebrow="THÔNG TIN CỦA BẠN" backHref={user.role === "parent" ? "/parent" : "/student"}>
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
  const [slots, setSlots] = useState([]);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [aiAvailable, setAiAvailable] = useState(false);
  const [preview, setPreview] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setError("");
    try {
      const dashboard = await api(`/api/dashboard/student?username=${encodeURIComponent(user.username)}`, { token });
      if (!Array.isArray(dashboard.schedule)) {
        throw new Error("Máy chủ trả về thời khóa biểu không đúng định dạng. Vui lòng tải lại trang hoặc báo quản trị viên.");
      }
      setSlots(dashboard.schedule.filter((slot) => slot && typeof slot === "object"));
    } catch (loadError) { setError(loadError.message); }
    try {
      const ai = await api("/api/schedule/import-image/status");
      setAiAvailable(Boolean(ai?.available));
    } catch (aiError) {
      setAiAvailable(false);
      setError(`Không kiểm tra được chức năng nhận diện lịch từ ảnh: ${aiError.message}`);
    }
  }, [token, user.username]);
  useEffect(() => { load(); }, [load]);

  const addSlot = async (event) => {
    event.preventDefault();
    setError(""); setMessage("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const result = await api("/api/schedule/slot", {
        method: "PUT", token,
        body: JSON.stringify({
          username: user.username,
          session: String(form.get("session")),
          day: String(form.get("day")),
          period: Number(form.get("period")),
          subject: String(form.get("subject")).trim(),
          lecturer: String(form.get("lecturer") || "").trim(),
        }),
      });
      setMessage(result.message);
      setError("");
      formElement.reset();
      await load();
    } catch (saveError) { setError(saveError.message); }
  };

  const removeSlot = async (slot) => {
    setError(""); setMessage("");
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
      await load();
    } catch (removeError) { setError(removeError.message); }
  };

  const importImage = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setBusy(true); setError(""); setMessage(""); setPreview([]);
    const body = new FormData();
    body.append("file", file);
    try {
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
    try {
      const result = await api("/api/schedule/slots", {
        method: "POST", token,
        body: JSON.stringify({ slots: preview.map((slot) => ({ ...slot, username: user.username })) }),
      });
      setMessage(result.message);
      setError("");
      setPreview([]);
      await load();
    } catch (saveError) { setError(saveError.message); }
    finally { setBusy(false); }
  };

  return <PageFrame title="Thời khóa biểu" eyebrow="SẮP XẾP LỊCH HỌC" backHref="/student">
    {(error || message) && <div className={`message ${error ? "message-error" : "message-success"}`} role={error ? "alert" : "status"}>{error || message}</div>}
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">THÊM TIẾT HỌC</p><h2>Nhập lịch học</h2></div></div>
      <form className="settings-form schedule-form" onSubmit={addSlot}>
        <div className="form-row">
          <label className="field"><span>Buổi</span><select name="session"><option value="morning">Buổi sáng</option><option value="afternoon">Buổi chiều</option></select></label>
          <label className="field"><span>Thứ</span><select name="day">{["2", "3", "4", "5", "6", "7"].map((day) => <option key={day} value={day}>Thứ {day}</option>)}</select></label>
        </div>
        <div className="form-row">
          <label className="field"><span>Tiết</span><select name="period">{[1, 2, 3, 4, 5, 6, 7].map((period) => <option key={period}>{period}</option>)}</select></label>
          <Field label="Môn học" name="subject" required maxLength="100" />
        </div>
        <Field label="Giáo viên (không bắt buộc)" name="lecturer" maxLength="100" />
        <div className="toolbar-actions"><button className="button button-primary">Lưu tiết học</button>
          {aiAvailable && <label className={`button button-quiet file-button ${busy ? "disabled" : ""}`}>Tạo thời khóa biểu từ ảnh<input type="file" accept="image/jpeg,image/png,image/webp" onChange={importImage} disabled={busy} /></label>}
        </div>
      </form>
    </section>
    {preview.length > 0 && <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">KIỂM TRA KẾT QUẢ AI</p><h2>Xem trước lịch nhận diện</h2></div><button className="button button-primary" onClick={savePreview} disabled={busy}>Lưu {preview.length} tiết</button></div>
      <p className="section-help">Hãy kiểm tra nội dung trước khi lưu. Kết quả AI có thể đọc nhầm ảnh.</p>
      <SlotList slots={preview} onRemove={(slot) => setPreview((items) => items.filter((item) => item !== slot))} />
    </section>}
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">LỊCH HIỆN TẠI</p><h2>{slots.length} tiết học</h2></div></div>
      {slots.length ? <ScheduleGrid slots={slots} onRemove={removeSlot} /> : <EmptyState title="Chưa có lịch học" text="Thêm tiết học bằng biểu mẫu hoặc nhận diện từ ảnh." />}
    </section>
  </PageFrame>;
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
      if (!sessionSlots.length) return null;
      return <div className="schedule-grid-section" key={session}>
        <h3>{label}</h3>
        <div className="schedule-table-scroll" role="region" aria-label={`Thời khóa biểu ${label.toLowerCase()}`} tabIndex="0">
          <table className="schedule-table">
            <thead><tr><th scope="col">Tiết</th>{["2", "3", "4", "5", "6", "7"].map((day) => <th scope="col" key={day}>Thứ {day}</th>)}</tr></thead>
            <tbody>{[1, 2, 3, 4, 5, 6, 7].map((period) => <tr key={period}>
              <th scope="row">{period}</th>
              {["2", "3", "4", "5", "6", "7"].map((day) => {
                const lessons = sessionSlots.filter((slot) => String(slot.day) === day && Number(slot.period) === period);
                return <td key={day}>{lessons.map((slot, index) => <article className="schedule-cell-lesson" key={`${slot.id || slot.subject}-${index}`}>
                  <strong>{slot.subject || "Chưa có tên môn"}</strong>
                  {slot.lecturer && <small>{slot.lecturer}</small>}
                  <button className="button button-quiet button-small" onClick={() => onRemove(slot)} aria-label={`Xóa ${slot.subject || "tiết học"} thứ ${day}, tiết ${period}`}>Xóa</button>
                </article>)}</td>;
              })}
            </tr>)}</tbody>
          </table>
        </div>
      </div>;
    })}
    {!validSlots.length && <EmptyState title="Chưa có tiết hợp lệ để hiển thị" text="Kiểm tra lại dữ liệu thời khóa biểu hoặc tải lại trang." />}
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
  const [permission, setPermission] = useState("Notification" in window ? Notification.permission : "unsupported");

  const load = useCallback(async () => {
    try {
      const [preferences, pushStatus] = await Promise.all([
        api(`/api/push/preferences?username=${encodeURIComponent(user.username)}`, { token }),
        api(`/api/push/status?username=${encodeURIComponent(user.username)}`, { token }),
      ]);
      setPrefs(preferences.reminders);
      setStatus(pushStatus);
    } catch (loadError) { setError(loadError.message); }
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

  return <PageFrame title="Thông báo & nhắc việc" eyebrow="NHẮC ĐÚNG LÚC" backHref={user.role === "parent" ? "/parent" : "/student"}>
    {(error || message) && <div className={`message ${error ? "message-error" : "message-success"}`} role={error ? "alert" : "status"}>{error || message}</div>}
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">THIẾT BỊ NÀY</p><h2>Thông báo đẩy</h2></div><span className="priority">{permission === "granted" ? "Được cho phép" : permission === "denied" ? "Đang bị chặn" : "Chưa bật"}</span></div>
      <p className="section-help">Bật thông báo để nhận nhắc hạn và cập nhật trên thiết bị này. Trên iPhone/iPad cần mở StudySync từ Màn hình chính.</p>
      <div className="toolbar-actions"><button className="button button-primary" onClick={enableNotifications} disabled={busy}>{busy ? "Đang bật..." : "Bật thông báo trên thiết bị này"}</button><button className="button button-quiet" onClick={testPush}>Gửi thông báo thử</button></div>
      {!status?.ready && <p className="inline-error">Firebase push chưa sẵn sàng trên backend.</p>}
      <div className="device-list">{(status?.devices || []).map((device) => <div className="device-row" key={device.id}><span><strong>{device.label || (device.device_type === "mobile" ? "Điện thoại" : "Trình duyệt")}</strong><small>Hoạt động lần cuối: {device.last_seen_at || "chưa rõ"}</small></span><button className="button button-quiet button-small" onClick={() => removeDevice(device.id)}>Tắt thiết bị</button></div>)}</div>
    </section>
    <section className="panel">
      <div className="panel-heading"><div><p className="eyebrow">CÁ NHÂN HÓA</p><h2>Cài đặt nhắc nhở</h2></div></div>
      {!prefs ? <LoadingState /> : <>
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

function StudentDashboard({ data, user, token, onChanged, onSuccess }) {
  const stats = data.stats || {};
  const tasks = data.assignments || [];
  const pendingTasks = tasks.filter((task) => !task.completed);
  const [showCreate, setShowCreate] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [taskError, setTaskError] = useState("");

  const updateTask = async (task, action) => {
    setBusyId(String(task.id));
    setTaskError("");
    try {
      if (action === "delete") {
        await api(`/api/assignments/${encodeURIComponent(task.id)}?username=${encodeURIComponent(user.username)}`, { method: "DELETE", token });
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
      setTaskError(error.message);
    } finally {
      setBusyId("");
    }
  };

  const createTask = async (event) => {
    event.preventDefault();
    setTaskError("");
    const values = new FormData(event.currentTarget);
    const payload = {
      title: String(values.get("title")).trim(),
      subject: String(values.get("subject")).trim(),
      description: String(values.get("description") || "").trim(),
      due_date: String(values.get("due_date")),
      due_time: String(values.get("due_time") || "23:59"),
      priority: String(values.get("priority")),
      username: user.username,
    };
    try {
      await api("/api/assignments", { method: "POST", token, body: JSON.stringify(payload) });
      setShowCreate(false);
      onSuccess("Đã thêm nhiệm vụ mới.");
      onChanged();
    } catch (error) {
      setTaskError(error.message);
    }
  };

  return <>
    <section className="stats-grid">
      <StatCard label="Tổng nhiệm vụ" value={stats.total ?? tasks.length} icon="▤" tone="blue" />
      <StatCard label="Đang chờ" value={stats.pending ?? pendingTasks.length} icon="◷" tone="amber" />
      <StatCard label="Đã hoàn thành" value={stats.completed ?? tasks.length - pendingTasks.length} icon="✓" tone="green" />
      <StatCard label="Tiến độ" value={`${stats.completion_rate ?? 0}%`} icon="↗" tone="violet" />
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
            <label className="field"><span>Hạn hoàn thành</span><input name="due_date" type="date" required min={new Date().toISOString().slice(0, 10)} /></label>
            <label className="field"><span>Giờ</span><input name="due_time" type="time" defaultValue="23:59" /></label>
          </div>
          <label className="field"><span>Ghi chú (không bắt buộc)</span><textarea name="description" rows="2" maxLength="500" placeholder="Thêm chi tiết để dễ nhớ..." /></label>
          <button className="button button-primary" type="submit">Lưu nhiệm vụ</button>
        </form>}
        {taskError && <p className="inline-error" role="alert">{taskError}</p>}
        {tasks.length ? <div className="task-list">
          {tasks.map((task) => <article className={`task-row ${task.completed ? "is-complete" : ""}`} key={task.id}>
            <button className={`check-button ${task.completed ? "checked" : ""}`} aria-label={task.completed ? "Đánh dấu chưa hoàn thành" : "Đánh dấu hoàn thành"} disabled={busyId === String(task.id)} onClick={() => updateTask(task, "toggle")}>{task.completed ? "✓" : ""}</button>
            <div className="task-main"><strong>{task.title}</strong><span>{task.subject || "Chưa phân loại"} · Hạn {task.due_date || "chưa đặt"}{task.due_time ? `, ${task.due_time}` : ""}</span></div>
            <span className={`priority priority-${String(task.priority || "trung bình").toLowerCase().replace(/\s/g, "-")}`}>{task.completed ? "Hoàn thành" : task.priority || "Trung bình"}</span>
            <button className="icon-button" aria-label={`Xóa ${task.title}`} disabled={busyId === String(task.id)} onClick={() => updateTask(task, "delete")}>×</button>
          </article>)}
        </div> : <EmptyState title="Chưa có nhiệm vụ nào" text="Thêm một việc cần làm để bắt đầu theo dõi tiến độ." />}
      </div>
      <aside className="side-column">
        <SchedulePanel schedule={data.schedule || []} />
        <LinkRequests user={user} token={token} onChanged={onChanged} />
      </aside>
    </section>
  </>;
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
