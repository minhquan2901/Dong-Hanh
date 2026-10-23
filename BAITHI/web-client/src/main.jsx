import React, { useCallback, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import { api, apiBaseUrl } from "./api";
import "./styles.css";

const USER_KEY = "study_sync_user";
const TOKEN_KEY = "study_sync_session_token";

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
    const clear = () => {
      localStorage.removeItem(USER_KEY);
      localStorage.removeItem(TOKEN_KEY);
      setSession(null);
      setNotice("Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.");
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
        <Dashboard session={session} onSignOut={signOut} />
      ) : (
        <AuthPanel
          mode={mode}
          setMode={setMode}
          authenticate={authenticate}
          notice={notice}
        />
      )}
      <footer className="footer">StudySync · Cùng xây dựng thói quen học tập tốt</footer>
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
        <p className="auth-hint">Bằng cách tiếp tục, bạn đồng ý sử dụng StudySync một cách an toàn và có trách nhiệm.</p>
      </section>
    </main>
  );
}

function Dashboard({ session, onSignOut }) {
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
  const legacyUrl = useMemo(() => {
    const base = apiBaseUrl || window.location.origin;
    return `${base}/${user.role === "parent" ? "parent" : "student"}`;
  }, [user.role]);

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
      <div className="legacy-callout">
        <div><strong>Cần thêm công cụ?</strong><span>Các cài đặt tài khoản, lịch chi tiết, PWA và thông báo đang có trong phiên bản đầy đủ.</span></div>
        <a className="button button-quiet" href={legacyUrl} target="_blank" rel="noreferrer">Mở phiên bản đầy đủ ↗</a>
      </div>
    </main>
  );
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
        </div> : <EmptyState title="Chưa liên kết học sinh" text="Mở phiên bản đầy đủ để gửi yêu cầu liên kết bằng mã học sinh." />}
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
    {schedule.length ? <div className="schedule-list">{schedule.slice(0, 5).map((lesson, index) => <article className="schedule-row" key={`${lesson.day}-${lesson.period}-${index}`}><span className="schedule-day">Thứ {lesson.day}</span><div><strong>{lesson.subject}</strong><small>Tiết {lesson.period} · {lesson.session === "morning" ? "Buổi sáng" : "Buổi chiều"}</small></div></article>)}</div> : <EmptyState title="Chưa có lịch học" text="Bạn có thể thêm thời khóa biểu trong phiên bản đầy đủ." />}
  </section>;
}

function LinkRequests({ user, token, onChanged }) {
  const [requests, setRequests] = useState([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try {
      const response = await api(`/api/student/link-requests?username=${encodeURIComponent(user.username)}`, { token });
      setRequests(response.requests || []);
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
