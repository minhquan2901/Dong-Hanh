import { useEffect, useMemo, useState } from "react";
import materialCatalog from "./materialCatalog.json";
import "./study-demo.css";

const materials = [
  { icon: "∑", title: "Đại số · Phương trình bậc nhất", meta: "Bài học · 12 phút", tag: "Toán học", tone: "mint", progress: 68 },
  { icon: "文", title: "Thì hiện tại hoàn thành", meta: "Thẻ ghi nhớ · 18 thẻ", tag: "Tiếng Anh", tone: "peach", progress: 42 },
  { icon: "⚛", title: "Chuyển động và vận tốc", meta: "Video · 08 phút", tag: "Vật lý", tone: "lavender", progress: 0 },
];

const initialTasks = [
  { id: 1, title: "Hoàn thành bài tập phương trình", subject: "Toán học", date: "Hôm nay, 20:00", color: "green", completed: false },
  { id: 2, title: "Ôn 18 từ vựng Unit 6", subject: "Tiếng Anh", date: "Ngày mai, 08:00", color: "orange", completed: false },
  { id: 3, title: "Đọc trước bài Chuyển động", subject: "Vật lý", date: "Thứ Sáu, 15:30", color: "purple", completed: false },
];

const libraryMaterials = materialCatalog.map((material) => ({
  ...material,
  icon: material.subject === "Toán" ? "∑" : material.subject === "Ngữ văn" ? "文" : "A",
  meta: `${material.subject} · Lớp ${material.grade}${material.volume ? ` · Tập ${material.volume}` : ""}`,
  tag: material.subject,
  tone: material.subject === "Toán" ? "mint" : material.subject === "Ngữ văn" ? "peach" : "blue",
  progress: 0,
}));

const demoPageNames = {
  overview: "Tổng quan",
  courses: "Khóa học",
  materials: "Tài liệu",
  schedule: "Thời khóa biểu",
  progress: "Tiến độ học tập",
  tasks: "Nhiệm vụ",
};

function getDemoPage() {
  const hash = window.location.hash.slice(1);
  if (hash.startsWith("material-")) return "Tài liệu";
  return demoPageNames[hash] || "Tổng quan";
}

function getMaterialHref(title) {
  const slug = title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return `#material-${slug}`;
}

function Icon({ name, size = 20 }) {
  const paths = {
    search: <><circle cx="11" cy="11" r="7" /><path d="m16 16 4 4" /></>,
    home: <><path d="m3 10 9-7 9 7" /><path d="M5 9v11h14V9M9 20v-7h6v7" /></>,
    book: <><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v17H6.5A2.5 2.5 0 0 1 4 17.5z" /><path d="M4 16.5A2.5 2.5 0 0 1 6.5 14H20M8 7h7" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M16 3v4M8 3v4M3 10h18" /></>,
    chart: <><path d="M4 19V5M4 19h17" /><path d="m7 15 4-4 3 2 6-7" /></>,
    sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.93 4.93l1.42 1.42m11.3 11.3 1.42 1.42M2 12h2m16 0h2M4.93 19.07l1.42-1.42m11.3-11.3 1.42-1.42" /></>,
    moon: <path d="M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13Z" />,
    arrow: <><path d="M5 12h14" /><path d="m13 6 6 6-6 6" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    check: <path d="m5 12 4 4L19 6" />,
    bell: <><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4" /></>,
    more: <><circle cx="5" cy="12" r="1" /><circle cx="12" cy="12" r="1" /><circle cx="19" cy="12" r="1" /></>,
    fire: <path d="M12 22c4.4 0 7-3.1 7-7 0-2.7-1.3-5-3.5-7-.2 2-1.1 3.2-2.5 3.7C13.6 7.9 12 4.9 9 2c.2 4.4-1.1 6.2-3 8-1.3 1.3-2 3-2 5 0 4 3 7 8 7Z" />,
    camera: <><path d="M14 5h-4L8 7H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3z" /><circle cx="12" cy="13" r="3" /></>,
    sparkle: <><path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" /><path d="m19 15 .9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9z" /></>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

export default function StudyCompanionDemo() {
  const [dark, setDark] = useState(false);
  const [query, setQuery] = useState("");
  const [activeNav, setActiveNav] = useState(getDemoPage);
  const [currentHash, setCurrentHash] = useState(window.location.hash);
  const [tasks, setTasks] = useState(initialTasks);
  const selectedMaterial = useMemo(
    () => libraryMaterials.find((item) => getMaterialHref(item.title) === currentHash) || null,
    [currentHash],
  );
  const doneCount = 4 + tasks.filter((task) => task.completed).length;
  const filteredMaterials = useMemo(
    () => libraryMaterials.filter((item) => `${item.title} ${item.tag} ${item.grade} ${item.volume || ""}`.toLowerCase().includes(query.toLowerCase())),
    [query],
  );
  const navItems = [
    { title: "Tổng quan", icon: "home", href: "#overview" },
    { title: "Khóa học", icon: "book", href: "#courses" },
    { title: "Tài liệu", icon: "book", href: "#materials" },
    { title: "Thời khóa biểu", icon: "calendar", href: "#schedule" },
    { title: "Tiến độ học tập", icon: "chart", href: "#progress" },
    { title: "Nhiệm vụ", icon: "check", href: "#tasks" },
  ];

  useEffect(() => {
    const syncPage = () => {
      setCurrentHash(window.location.hash);
      setActiveNav(getDemoPage());
    };
    window.addEventListener("hashchange", syncPage);
    return () => window.removeEventListener("hashchange", syncPage);
  }, []);

  return (
    <div className={`study-demo${dark ? " is-dark" : ""}`}>
      <header className="demo-header">
        <a className="demo-brand" href="#overview" aria-label="Đồng hành học tập cùng bạn">
          <span className="demo-brand-mark"><Icon name="book" size={21} /></span>
          <span className="demo-brand-name">đồng hành<span>học tập cùng bạn</span></span>
        </a>
        <label className="demo-search">
          <Icon name="search" size={18} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Tìm khóa học, tài liệu..." aria-label="Tìm kiếm" />
          <kbd>⌘ K</kbd>
        </label>
        <nav className="demo-top-nav" aria-label="Điều hướng chính">
          {navItems.slice(1, 4).map((item) => (
            <a key={item.title} href={item.href} aria-current={activeNav === item.title ? "page" : undefined}>{item.title === "Thời khóa biểu" ? "Lịch học" : item.title}</a>
          ))}
        </nav>
        <div className="demo-header-actions">
          <button className="demo-icon-button" aria-label={dark ? "Bật giao diện sáng" : "Bật giao diện tối"} onClick={() => setDark(!dark)}><Icon name={dark ? "sun" : "moon"} size={19} /></button>
          <button className="demo-icon-button demo-notification" aria-label="Thông báo"><Icon name="bell" size={19} /><i /></button>
          <a className="demo-profile" href="#profile"><span className="demo-avatar">MA</span><span className="demo-profile-name">Minh Anh<small>Học sinh lớp 8/1</small></span><span className="demo-chevron">⌄</span></a>
        </div>
      </header>

      <div className="demo-layout">
        <aside className="demo-sidebar">
          <p className="demo-sidebar-label">KHÔNG GIAN HỌC TẬP</p>
          <nav className="demo-side-nav" aria-label="Điều hướng">
            {navItems.map((item) => (
              <a key={item.title} className={activeNav === item.title ? "active" : ""} href={item.href} aria-current={activeNav === item.title ? "page" : undefined}>
                <Icon name={item.icon} size={19} /><span>{item.title}</span>{item.title === "Tài liệu" && <span className="demo-nav-count">12</span>}
              </a>
            ))}
          </nav>
          <div className="demo-sidebar-bottom">
            <div className="demo-streak-card"><div className="demo-streak-icon"><Icon name="fire" size={20} /></div><strong>7 ngày</strong><span>Chuỗi học tập của bạn</span><div className="demo-week-dots"><b>T2</b><b>T3</b><b>T4</b><b>T5</b><b>T6</b><b>T7</b><b>CN</b></div></div>
            <a className="demo-help-link" href="#help">Trợ giúp & hỗ trợ <Icon name="arrow" size={15} /></a>
          </div>
        </aside>
        <nav className="demo-mobile-nav" aria-label="Điều hướng trên điện thoại">
          {navItems.map((item) => (
            <a key={item.title} className={activeNav === item.title ? "active" : ""} href={item.href} aria-current={activeNav === item.title ? "page" : undefined}>
              <Icon name={item.icon} size={18} /><span>{item.title === "Thời khóa biểu" ? "Lịch học" : item.title === "Tiến độ học tập" ? "Tiến độ" : item.title}</span>
            </a>
          ))}
        </nav>

        <main className="demo-main" id="overview">
          {activeNav === "Tổng quan" ? <>
          <div className="demo-welcome">
            <div className="demo-welcome-copy">
              <span className="demo-date">THỨ NĂM, 29 THÁNG 10, 2026 <span className="demo-live-dot" /> NGÀY HỌC TỐT LÀNH</span>
              <h1>Mỗi ngày một chút,<br /><span>bạn đang tiến bộ!</span> <span className="demo-wave">✳</span></h1>
              <p>Bạn đã hoàn thành <strong>{doneCount} nhiệm vụ</strong> trong tuần này. Cùng tiếp tục nhé!</p>
              <a className="demo-primary-button" href="#courses">Tiếp tục học <Icon name="arrow" size={17} /></a>
            </div>
            <div className="demo-hero-art" aria-hidden="true">
              <div className="demo-art-sun" /><div className="demo-art-orbit" /><div className="demo-art-book"><span>✦</span></div>
              <div className="demo-art-leaf leaf-a" /><div className="demo-art-leaf leaf-b" /><div className="demo-art-star">✳</div>
              <div className="demo-art-caption">Grow at your<br />own pace <span>↗</span></div>
            </div>
          </div>

          <section className="demo-stats" aria-label="Tổng quan học tập">
            <article className="demo-stat-card"><span className="demo-stat-icon soft-green"><Icon name="chart" size={19} /></span><span className="demo-stat-label">Tiến độ tuần này</span><strong>72<span>%</span></strong><div className="demo-progress-track"><i style={{ width: "72%" }} /></div><small><b>+12%</b> so với tuần trước</small></article>
            <article className="demo-stat-card"><span className="demo-stat-icon soft-orange"><Icon name="fire" size={19} /></span><span className="demo-stat-label">Chuỗi ngày học</span><strong>7 <em>ngày</em></strong><div className="demo-stat-foot"><span className="demo-mini-dots"><i /><i /><i /><i /><i /><i /><i /></span><small>Kỷ lục: 12 ngày</small></div></article>
            <article className="demo-stat-card"><span className="demo-stat-icon soft-violet"><Icon name="clock" size={19} /></span><span className="demo-stat-label">Thời gian học</span><strong>8.5 <em>giờ</em></strong><div className="demo-stat-foot"><span className="demo-stat-note">Mục tiêu tuần: 10 giờ</span><small>85% hoàn thành</small></div></article>
            <article className="demo-stat-card"><span className="demo-stat-icon soft-blue"><Icon name="check" size={19} /></span><span className="demo-stat-label">Nhiệm vụ hoàn thành</span><strong>{doneCount}<em>/ 7</em></strong><div className="demo-stat-foot"><span className="demo-stat-note">Còn {tasks.filter((task) => !task.completed).length} nhiệm vụ</span><small>Tuần này</small></div></article>
          </section>

          <div className="demo-content-grid">
            <div className="demo-primary-column">
              <section className="demo-section" id="courses">
                <div className="demo-section-heading"><div><span className="demo-kicker">HÀNH TRÌNH CỦA BẠN</span><h2>Khóa học đang học</h2></div><a href="#courses">Tất cả khóa học <Icon name="arrow" size={15} /></a></div>
                <div className="demo-course-card">
                  <div className="demo-course-art math-art"><span>∑</span><i>π</i><b>×</b></div>
                  <div className="demo-course-info"><span className="demo-subject-tag">TOÁN HỌC <i>·</i> LỚP 8</span><h3>Chinh phục Đại số</h3><p>Chương 3 · Phương trình và hàm số</p><div className="demo-course-progress"><div className="demo-progress-track"><i style={{ width: "68%" }} /></div><span>68%</span></div><a className="demo-course-link" href="#materials">Tiếp tục bài học <Icon name="arrow" size={15} /></a></div>
                  <div className="demo-course-decoration">✳</div>
                </div>
              </section>

              <section className="demo-section" id="materials">
                <div className="demo-section-heading"><div><span className="demo-kicker">DÀNH RIÊNG CHO BẠN</span><h2>Tài liệu gợi ý</h2></div><a href="#materials">Khám phá thêm <Icon name="arrow" size={15} /></a></div>
                <div className="demo-material-list">
                  {filteredMaterials.slice(0, 3).length ? filteredMaterials.slice(0, 3).map((item) => (
                    <a className="demo-material-card" href={getMaterialHref(item.title)} key={item.title}>
                      <span className={`demo-material-icon ${item.tone}`}>{item.icon}</span>
                      <span className="demo-material-info"><strong>{item.title}</strong><small>{item.meta}</small></span>
                      <span className="demo-material-tag">{item.tag}</span>
                      {item.progress > 0 && <span className="demo-material-progress"><i style={{ width: `${item.progress}%` }} /></span>}
                      <span className="demo-material-arrow"><Icon name="arrow" size={17} /></span>
                    </a>
                  )) : <p className="demo-no-results">Không tìm thấy tài liệu phù hợp.</p>}
                </div>
              </section>
            </div>

            <aside className="demo-right-column">
              <section className="demo-section demo-tasks-section">
                <div className="demo-section-heading"><div><span className="demo-kicker">ĐỪNG QUÊN NHÉ</span><h2>Việc cần làm</h2></div><button className="demo-more-button" aria-label="Thêm lựa chọn"><Icon name="more" size={20} /></button></div>
                <div className="demo-task-list">
                  {tasks.length ? tasks.map((task) => (
                    <label className="demo-task" key={task.id}>
                      <input type="checkbox" checked={Boolean(task.completed)} onChange={() => setTasks((current) => current.map((entry) => entry.id === task.id ? { ...entry, completed: !entry.completed } : entry))} />
                      <span className={`demo-task-check ${task.color}`}><Icon name="check" size={14} /></span>
                      <span className="demo-task-content"><strong>{task.title}</strong><small>{task.subject}</small><small className="demo-task-date"><Icon name="clock" size={13} /> {task.date}</small></span>
                    </label>
                  )) : <p className="demo-all-done"><span>✦</span> Tuyệt vời! Bạn đã hoàn thành tất cả.</p>}
                </div>
                <a className="demo-view-all" href="#tasks">Xem tất cả nhiệm vụ <Icon name="arrow" size={15} /></a>
              </section>

              <section className="demo-section demo-schedule" id="schedule">
                <div className="demo-section-heading"><div><span className="demo-kicker">THỨ NĂM, 29/10</span><h2>Lịch học hôm nay</h2></div><a className="demo-calendar-link" href="#schedule"><Icon name="calendar" size={17} /></a></div>
                <div className="demo-timeline">
                  <div className="demo-class"><time>08:00</time><i className="timeline-dot mint-dot" /><div><strong>Tiếng Anh</strong><small>Unit 6 · Phòng học ảo</small></div><b className="class-now">Đã học</b></div>
                  <div className="demo-class upcoming"><time>14:30</time><i className="timeline-dot green-dot" /><div><strong>Toán học</strong><small>Đại số · Buổi 12</small></div><b>Sắp tới</b></div>
                  <div className="demo-class"><time>16:00</time><i className="timeline-dot blue-dot" /><div><strong>Vật lý</strong><small>Chuyển động · Ôn tập</small></div></div>
                </div>
              </section>
            </aside>
          </div>
          <footer className="demo-footer" id="profile">Học theo cách của bạn, tiến bộ theo nhịp riêng <span>✳</span></footer>
          </> : <DemoNavigationPage page={activeNav} query={query} materials={filteredMaterials} selectedMaterial={selectedMaterial} tasks={tasks} setTasks={setTasks} />}
        </main>
      </div>
    </div>
  );
}

function DemoNavigationPage({ page, query, materials: visibleMaterials, selectedMaterial, tasks, setTasks }) {
  const [subjectFilter, setSubjectFilter] = useState("all");
  const [gradeFilter, setGradeFilter] = useState("all");
  const [volumeFilter, setVolumeFilter] = useState("all");
  const filteredMaterials = visibleMaterials.filter((material) => (
    (subjectFilter === "all" || material.subject === subjectFilter)
    && (gradeFilter === "all" || String(material.grade) === gradeFilter)
    && (volumeFilter === "all" || String(material.volume || "") === volumeFilter)
  ));
  const pageInfo = {
    "Khóa học": ["KHÔNG GIAN HỌC TẬP", "Khóa học của bạn", "Theo dõi hành trình và tiếp tục bài học còn dang dở."],
    "Tài liệu": ["THƯ VIỆN HỌC TẬP", "Tài liệu học tập", "Tìm lại bài học, video và thẻ ghi nhớ của bạn."],
    "Thời khóa biểu": ["KẾ HOẠCH HỌC TẬP", "Thời khóa biểu", "Lịch học trong tuần giúp bạn chủ động sắp xếp thời gian."],
    "Tiến độ học tập": ["NHÌN LẠI HÀNH TRÌNH", "Tiến độ học tập", "Ghi nhận từng bước nhỏ và giữ nhịp học tập đều đặn."],
    "Nhiệm vụ": ["KẾ HOẠCH CỦA BẠN", "Nhiệm vụ học tập", "Ghi lại điều cần làm, rồi tự hào đánh dấu khi bạn hoàn thành."],
  }[page];

  return <section className="demo-page-view" aria-live="polite">
    <div className="demo-page-heading">
      <a className="demo-back-link" href="#overview">← Tổng quan</a>
      <span className="demo-kicker">{pageInfo[0]}</span>
      <h1>{pageInfo[1]}</h1>
      <p>{pageInfo[2]}</p>
    </div>

    {page === "Khóa học" && <div className="demo-page-courses">
      <article className="demo-course-card">
        <div className="demo-course-art math-art"><span>∑</span><i>π</i><b>×</b></div>
        <div className="demo-course-info"><span className="demo-subject-tag">TOÁN HỌC <i>·</i> LỚP 8</span><h3>Chinh phục Đại số</h3><p>Chương 3 · Phương trình và hàm số</p><div className="demo-course-progress"><div className="demo-progress-track"><i style={{ width: "68%" }} /></div><span>68%</span></div><a className="demo-course-link" href="#materials">Tiếp tục bài học <Icon name="arrow" size={15} /></a></div>
      </article>
      <article className="demo-course-card">
        <div className="demo-course-art english-art"><span>文</span><i>A</i><b>✳</b></div>
        <div className="demo-course-info"><span className="demo-subject-tag">TIẾNG ANH <i>·</i> LỚP 8</span><h3>English around us</h3><p>Unit 6 · Life on other planets</p><div className="demo-course-progress"><div className="demo-progress-track"><i style={{ width: "42%" }} /></div><span>42%</span></div><a className="demo-course-link" href="#materials">Tiếp tục bài học <Icon name="arrow" size={15} /></a></div>
      </article>
    </div>}

    {page === "Tài liệu" && selectedMaterial && <article className="demo-material-detail">
      <a className="demo-back-link" href="#materials">← Tất cả tài liệu</a>
      <div className={`demo-material-icon ${selectedMaterial.tone}`}>{selectedMaterial.icon}</div>
      <span className="demo-subject-tag">{selectedMaterial.tag.toUpperCase()}</span>
      <h2>{selectedMaterial.title}</h2>
      <p>{selectedMaterial.meta}. PDF được mở từ Google Drive sau khi có link chia sẻ.</p>
      <div className="demo-detail-progress"><span>Nguồn PDF</span><strong>{selectedMaterial.sourceUrl ? "Có sẵn" : "Chưa liên kết"}</strong></div>
      {selectedMaterial.sourceUrl ? <a className="demo-primary-button" href={selectedMaterial.sourceUrl} target="_blank" rel="noreferrer">Mở trên Drive <Icon name="arrow" size={17} /></a> : <span className="demo-material-source-note">Chưa thêm link chia sẻ Google Drive.</span>}
    </article>}

    {page === "Tài liệu" && !selectedMaterial && <div className="demo-page-materials">
      <p className="demo-material-source-note">Tài liệu mở từ Google Drive, không làm tăng dung lượng deploy Vercel.</p>
      <div className="demo-library-toolbar">
        <span>{query ? `Kết quả tìm kiếm cho “${query}”` : `${filteredMaterials.length} tài liệu phù hợp`}</span>
        <label>Môn <select value={subjectFilter} onChange={(event) => setSubjectFilter(event.target.value)}><option value="all">Tất cả môn</option>{[...new Set(visibleMaterials.map((material) => material.subject))].map((subject) => <option key={subject} value={subject}>{subject}</option>)}</select></label>
        <label>Lớp <select value={gradeFilter} onChange={(event) => setGradeFilter(event.target.value)}><option value="all">Lớp 6–9</option>{[6, 7, 8, 9].map((grade) => <option key={grade} value={grade}>{`Lớp ${grade}`}</option>)}</select></label>
        <label>Tập <select value={volumeFilter} onChange={(event) => setVolumeFilter(event.target.value)}><option value="all">Tất cả tập</option><option value="1">Tập 1</option><option value="2">Tập 2</option><option value="">Không chia tập</option></select></label>
      </div>
      {filteredMaterials.length ? filteredMaterials.map((item) => (
        <a className="demo-material-card" href={getMaterialHref(item.title)} key={item.id}>
          <span className={`demo-material-icon ${item.tone}`}>{item.icon}</span>
          <span className="demo-material-info"><strong>{item.title}</strong><small>{item.meta}</small></span>
          <span className="demo-material-tag">{item.tag}</span>
          {item.progress > 0 && <span className="demo-material-progress"><i style={{ width: `${item.progress}%` }} /></span>}
          <span className="demo-material-arrow"><Icon name="arrow" size={17} /></span>
        </a>
      )) : <p className="demo-no-results">Không tìm thấy tài liệu phù hợp. Thử đổi bộ lọc môn, lớp hoặc tập nhé.</p>}
    </div>}

    {page === "Thời khóa biểu" && <DemoSchedule />}

    {page === "Nhiệm vụ" && <DemoTasks tasks={tasks} setTasks={setTasks} />}

    {page === "Tiến độ học tập" && <div className="demo-progress-page">
      <section className="demo-progress-summary"><span className="demo-stat-icon soft-green"><Icon name="chart" size={19} /></span><span className="demo-stat-label">Tiến độ hoàn thành tuần này</span><strong>72<span>%</span></strong><div className="demo-progress-track"><i style={{ width: "72%" }} /></div><small><b>+12%</b> so với tuần trước · Mục tiêu tuần: 80%</small></section>
      <section className="demo-streak-summary"><span className="demo-stat-icon soft-orange"><Icon name="fire" size={19} /></span><span className="demo-stat-label">Chuỗi ngày học liên tiếp</span><strong>7 <em>ngày</em></strong><div className="demo-week-dots"><b>T2</b><b>T3</b><b>T4</b><b>T5</b><b>T6</b><b>T7</b><b>CN</b></div><small>Chỉ còn 5 ngày để lập kỷ lục mới!</small></section>
      <section className="demo-section demo-progress-tasks"><div className="demo-section-heading"><div><span className="demo-kicker">MỤC TIÊU TUẦN</span><h2>Nhiệm vụ đang theo dõi</h2></div></div>
        {tasks.length ? tasks.map((task) => <label className="demo-task" key={task.id}><input type="checkbox" checked={Boolean(task.completed)} onChange={() => setTasks((current) => current.map((entry) => entry.id === task.id ? { ...entry, completed: !entry.completed } : entry))} /><span className={`demo-task-check ${task.color}`}><Icon name="check" size={14} /></span><span className="demo-task-content"><strong>{task.title}</strong><small>{task.subject}</small><small className="demo-task-date"><Icon name="clock" size={13} /> {task.date}</small></span></label>) : <p className="demo-all-done"><span>✦</span> Tuyệt vời! Bạn đã hoàn thành tất cả.</p>}
      </section>
    </div>}
  </section>;
}

function DemoTasks({ tasks, setTasks }) {
  const [filter, setFilter] = useState("all");
  const [deleteCandidate, setDeleteCandidate] = useState(null);
  const [title, setTitle] = useState("");
  const [subject, setSubject] = useState("Toán học");
  const localToday = new Date();
  localToday.setMinutes(localToday.getMinutes() - localToday.getTimezoneOffset());
  const today = localToday.toISOString().slice(0, 10);
  const pending = tasks.filter((task) => !task.completed).length;
  const completed = tasks.length - pending;
  const visibleTasks = tasks.filter((task) => (
    filter === "all" || (filter === "pending" && !task.completed) || (filter === "completed" && task.completed)
  ));

  const addTask = (event) => {
    event.preventDefault();
    const formData = new FormData(event.currentTarget);
    const dueDate = new Date(`${formData.get("due_date")}T12:00:00`).toLocaleDateString("vi-VN", { day: "numeric", month: "short" });
    const colors = { "Toán học": "green", "Tiếng Anh": "orange", "Vật lý": "purple", "Ngữ văn": "green" };
    setTasks((current) => [...current, {
      id: Date.now(),
      title: title.trim(),
      subject,
      date: `Hạn ${dueDate}`,
      color: colors[subject] || "green",
      completed: false,
    }]);
    setTitle("");
  };

  return <div className="demo-task-page">
    <form className="demo-task-add-form" onSubmit={addTask}>
      <label className="demo-task-add-title"><span>＋</span><input value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={120} placeholder="Thêm nhiệm vụ học tập mới hôm nay..." aria-label="Tên nhiệm vụ mới" /></label>
      <div className="demo-task-add-fields">
        <label><span>Môn học</span><select value={subject} onChange={(event) => setSubject(event.target.value)}><option>Toán học</option><option>Tiếng Anh</option><option>Vật lý</option><option>Ngữ văn</option><option>Khác</option></select></label>
        <label><span>Hạn hoàn thành</span><input type="date" name="due_date" min={today} defaultValue={today} required /></label>
        <button className="demo-primary-button" type="submit">Thêm nhiệm vụ <Icon name="arrow" size={16} /></button>
      </div>
    </form>

    <div className="demo-task-stats">
      <article><span className="task-stat-dot pending" /><span>Đang chờ</span><strong>{pending}</strong></article>
      <article><span className="task-stat-dot completed" /><span>Đã hoàn thành</span><strong>{completed}</strong></article>
      <article><span className="task-stat-dot progress" /><span>Tiến độ</span><strong>{tasks.length ? Math.round((completed / tasks.length) * 100) : 0}%</strong></article>
    </div>

    <section className="demo-task-manager">
      <div className="demo-task-manager-head">
        <div><span className="demo-kicker">KẾ HOẠCH CỦA BẠN</span><h2>Danh sách nhiệm vụ</h2></div>
        <div className="demo-task-filters" role="group" aria-label="Lọc nhiệm vụ">{[["all", "Tất cả"], ["pending", "Đang làm"], ["completed", "Đã xong"]].map(([value, label]) => <button key={value} type="button" className={filter === value ? "active" : ""} onClick={() => setFilter(value)}>{label}</button>)}</div>
      </div>
      <div className="demo-task-manager-list">
        {visibleTasks.length ? visibleTasks.map((task) => <article className={`demo-managed-task${task.completed ? " completed" : ""}${task.deleting ? " deleting" : ""}`} key={task.id} onAnimationEnd={(event) => { if (task.deleting && event.animationName === "task-card-exit") setTasks((current) => current.filter((entry) => entry.id !== task.id)); }}>
          <label className="demo-managed-check"><input type="checkbox" checked={Boolean(task.completed)} disabled={task.deleting} onChange={() => setTasks((current) => current.map((entry) => entry.id === task.id ? { ...entry, completed: !entry.completed } : entry))} /><span><Icon name="check" size={14} /></span></label>
          <div className="demo-managed-task-text"><strong>{task.title}</strong><small>{task.date}</small></div>
          <span className={`demo-managed-subject ${task.color}`}>{task.subject}</span>
          <button type="button" className="demo-managed-delete" title="Xóa nhiệm vụ" aria-label={`Xóa ${task.title}`} disabled={task.deleting} onClick={() => setDeleteCandidate(task)}><svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 6h18M8 6V4h8v2m3 0-1 14H6L5 6m4 4v6m6-6v6" /></svg></button>
        </article>) : <div className="demo-task-empty"><span>✿</span><strong>{filter === "completed" ? "Chưa có nhiệm vụ hoàn thành" : filter === "pending" ? "Bạn đã hoàn thành mọi việc!" : "Hôm nay thật thoáng đãng"}</strong><p>{filter === "pending" ? "Tuyệt vời! Bạn có thể thêm việc mới khi sẵn sàng." : "Thêm một nhiệm vụ nhỏ để bắt đầu kế hoạch học tập."}</p></div>}
      </div>
    </section>

    {deleteCandidate && <div className="demo-delete-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setDeleteCandidate(null); }}>
      <section className="demo-delete-dialog" role="alertdialog" aria-modal="true" aria-labelledby="demo-delete-title">
        <span className="demo-delete-warning">!</span><h2 id="demo-delete-title">Xóa nhiệm vụ này?</h2><p><strong>{deleteCandidate.title}</strong> sẽ bị xóa khỏi danh sách của bạn.</p>
        <div><button type="button" onClick={() => setDeleteCandidate(null)}>Giữ lại</button><button type="button" className="danger" onClick={() => { setTasks((current) => current.map((task) => task.id === deleteCandidate.id ? { ...task, deleting: true } : task)); setDeleteCandidate(null); }}>Xóa nhiệm vụ</button></div>
      </section>
    </div>}
  </div>;
}

const demoLessons = [
  { session: "morning", day: "2", period: 1, subject: "Toán học", teacher: "Cô Lan", tone: "mint" },
  { session: "morning", day: "2", period: 3, subject: "Ngữ văn", teacher: "Cô Hương", tone: "peach" },
  { session: "morning", day: "3", period: 2, subject: "Tiếng Anh", teacher: "Thầy Nam", tone: "blue" },
  { session: "morning", day: "3", period: 4, subject: "Vật lý", teacher: "Cô Mai", tone: "lavender" },
  { session: "morning", day: "4", period: 1, subject: "Hóa học", teacher: "Thầy Minh", tone: "yellow" },
  { session: "morning", day: "4", period: 3, subject: "Toán học", teacher: "Cô Lan", tone: "mint" },
  { session: "morning", day: "5", period: 2, subject: "Lịch sử", teacher: "Cô Hương", tone: "peach" },
  { session: "morning", day: "5", period: 5, subject: "Tiếng Anh", teacher: "Thầy Nam", tone: "blue" },
  { session: "morning", day: "6", period: 1, subject: "Sinh học", teacher: "Cô Mai", tone: "mint" },
  { session: "morning", day: "6", period: 4, subject: "Ngữ văn", teacher: "Cô Hương", tone: "peach" },
  { session: "morning", day: "7", period: 2, subject: "Toán học", teacher: "Cô Lan", tone: "mint" },
  { session: "afternoon", day: "2", period: 1, subject: "Tiếng Anh", teacher: "Thầy Nam", tone: "blue" },
  { session: "afternoon", day: "2", period: 3, subject: "Tin học", teacher: "Thầy Minh", tone: "lavender" },
  { session: "afternoon", day: "3", period: 2, subject: "Thể dục", teacher: "Thầy An", tone: "yellow" },
  { session: "afternoon", day: "4", period: 1, subject: "Ngữ văn", teacher: "Cô Hương", tone: "peach" },
  { session: "afternoon", day: "4", period: 4, subject: "Toán học", teacher: "Cô Lan", tone: "mint" },
  { session: "afternoon", day: "5", period: 2, subject: "Vật lý", teacher: "Cô Mai", tone: "lavender" },
  { session: "afternoon", day: "6", period: 1, subject: "Tiếng Anh", teacher: "Thầy Nam", tone: "blue" },
  { session: "afternoon", day: "7", period: 3, subject: "Mỹ thuật", teacher: "Cô Vy", tone: "peach" },
];

function DemoSchedule() {
  const [editing, setEditing] = useState(false);
  const [notice, setNotice] = useState("");
  const [lessons, setLessons] = useState(demoLessons);
  const [pendingLessons, setPendingLessons] = useState([]);
  const days = ["2", "3", "4", "5", "6", "7"];

  const buildLesson = (entry, period = entry.period) => ({
    session: entry.session,
    day: entry.day,
    period,
    subject: entry.subject,
    teacher: entry.teacher,
    tone: entry.tone || "mint",
  });

  const lessonTone = (subject) => {
    const value = subject.toLowerCase();
    if (value.includes("anh")) return "blue";
    if (value.includes("văn")) return "peach";
    if (value.includes("lý")) return "lavender";
    if (value.includes("hóa")) return "yellow";
    return "mint";
  };

  const readLessonForm = (form) => ({
    session: String(form.get("session")),
    day: String(form.get("day")),
    period: Number(form.get("period")),
    duration: Number(form.get("duration")),
    subject: String(form.get("subject") || "").trim(),
    teacher: String(form.get("teacher") || "").trim(),
  });

  const queueLesson = (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const entry = readLessonForm(new FormData(form));
    if (!entry.subject) return;
    if (entry.period + entry.duration - 1 > 5) {
      setNotice("Tiết đôi cần có tiết kế tiếp. Hãy chọn tiết bắt đầu từ 1 đến 4.");
      return;
    }

    const occupiedPeriods = Array.from({ length: entry.duration }, (_, index) => entry.period + index);
    setPendingLessons((current) => [
      ...current.filter((queued) => (
        queued.session !== entry.session
        || queued.day !== entry.day
        || !Array.from({ length: queued.duration }, (_, index) => queued.period + index)
          .some((period) => occupiedPeriods.includes(period))
      )),
      entry,
    ]);
    setNotice("");
    form.elements.subject.value = "";
    form.elements.teacher.value = "";
  };

  const saveLessons = (entries) => {
    if (!entries.length) {
      setNotice("Hãy thêm ít nhất một tiết vào danh sách chờ trước khi lưu.");
      return;
    }
    const newLessons = entries.flatMap((entry) => (
      Array.from({ length: entry.duration }, (_, index) => buildLesson(entry, entry.period + index))
    ));
    setLessons((current) => {
      const positions = new Map(current.map((lesson) => [
        `${lesson.session}:${lesson.day}:${lesson.period}`,
        lesson,
      ]));
      newLessons.forEach((lesson) => {
        positions.set(`${lesson.session}:${lesson.day}:${lesson.period}`, lesson);
      });
      return Array.from(positions.values());
    });
    setNotice(`Đã lưu ${entries.length} tiết học vào thời khóa biểu demo.`);
    setPendingLessons([]);
  };

  const addLessonImmediately = (event) => {
    event.preventDefault();
    const form = event.currentTarget.form;
    if (!form.reportValidity()) return;
    const entry = readLessonForm(new FormData(form));
    if (!entry.subject) return;
    if (entry.period + entry.duration - 1 > 5) {
      setNotice("Tiết đôi cần có tiết kế tiếp. Hãy chọn tiết bắt đầu từ 1 đến 4.");
      return;
    }
    saveLessons([entry]);
  };

  const removeLesson = (lesson) => {
    setLessons((current) => current.filter((entry) => !(
      entry.session === lesson.session && entry.day === lesson.day && entry.period === lesson.period
    )));
    setNotice(`Đã xóa ${lesson.subject} khỏi thời khóa biểu demo.`);
  };
  return <section className="demo-timetable-page">
    <div className="demo-timetable-toolbar">
      <div className="demo-timetable-week"><span className="demo-week-pill"><Icon name="calendar" size={15} /> Tuần hiện tại</span><span>Thứ Hai – Thứ Bảy · 26 – 31/10</span></div>
      <div className="demo-timetable-actions">
        <button type="button" className={`demo-edit-timetable${editing ? " selected" : ""}`} onClick={() => setEditing(!editing)}><Icon name="book" size={16} />{editing ? "Xong chỉnh sửa" : "Chỉnh sửa thời khóa biểu"}</button>
        <button type="button" className="demo-ai-timetable" onClick={() => setNotice("Nhận diện thời khóa biểu từ ảnh sẽ dùng được khi bạn đăng nhập vào tài khoản.")}><Icon name="sparkle" size={17} />Tạo từ ảnh</button>
      </div>
    </div>
    {notice && <p className="demo-timetable-notice" role="status">{notice}<button type="button" onClick={() => setNotice("")} aria-label="Đóng thông báo">×</button></p>}
    {editing && <form className="demo-timetable-editor" onSubmit={queueLesson}>
      <div className="demo-timetable-editor-heading"><span className="demo-kicker">THÊM TIẾT HỌC</span><strong>Nhập lịch học</strong></div>
      <div className="demo-timetable-editor-fields">
        <label><span>Buổi</span><select name="session"><option value="morning">Buổi sáng</option><option value="afternoon">Buổi chiều</option></select></label>
        <label><span>Thứ</span><select name="day">{days.map((day) => <option key={day} value={day}>Thứ {day}</option>)}</select></label>
        <label><span>Tiết</span><select name="period">{[1, 2, 3, 4, 5].map((period) => <option key={period} value={period}>{period}</option>)}</select></label>
        <label><span>Loại tiết</span><select name="duration"><option value="1">Tiết đơn</option><option value="2">Tiết đôi</option></select></label>
        <label><span>Môn học</span><input name="subject" required maxLength="100" placeholder="Ví dụ: Toán học" /></label>
        <label><span>Giáo viên (không bắt buộc)</span><input name="teacher" maxLength="100" placeholder="Tên giáo viên" /></label>
      </div>
      <div className="demo-timetable-editor-actions">
        <button type="submit" className="demo-editor-primary">Thêm vào danh sách</button>
        <button type="button" onClick={() => saveLessons(pendingLessons)}>Lưu tất cả ({pendingLessons.length})</button>
        <button type="button" onClick={() => setPendingLessons([])} disabled={!pendingLessons.length}>Xóa danh sách</button>
        <button type="button" onClick={addLessonImmediately}>Lưu tiết học ngay</button>
      </div>
      {pendingLessons.length > 0 && <div className="demo-timetable-pending" aria-live="polite">
        <strong>Danh sách chờ lưu ({pendingLessons.length})</strong>
        {pendingLessons.map((entry, index) => <div key={`${entry.session}-${entry.day}-${entry.period}-${index}`}>
          <span>{entry.session === "morning" ? "Sáng" : "Chiều"}, thứ {entry.day}, {entry.duration === 2 ? `tiết ${entry.period}-${entry.period + 1} · tiết đôi` : `tiết ${entry.period} · tiết đơn`}: {entry.subject}{entry.teacher ? ` · ${entry.teacher}` : ""}</span>
          <button type="button" onClick={() => setPendingLessons((current) => current.filter((_, itemIndex) => itemIndex !== index))}>Bỏ</button>
        </div>)}
      </div>}
    </form>}
    {["morning", "afternoon"].map((session) => <section className={`demo-timetable-session ${session}`} key={session}>
      <div className="demo-timetable-session-title"><span className="demo-session-icon">{session === "morning" ? "☀" : "☁"}</span><div><h2>{session === "morning" ? "Buổi sáng" : "Buổi chiều"}</h2><p>{session === "morning" ? "Bắt đầu ngày mới thật nhiều năng lượng" : "Tiếp tục chinh phục những điều mới"}</p></div><span className="demo-period-count">{lessons.filter((lesson) => lesson.session === session).length} tiết</span></div>
      <div className="demo-timetable-scroll" role="region" aria-label={`Thời khóa biểu ${session === "morning" ? "buổi sáng" : "buổi chiều"}`} tabIndex="0">
        <table className="demo-timetable-grid">
          <thead><tr><th scope="col">TIẾT</th>{days.map((day) => <th key={day} scope="col">THỨ {day}</th>)}</tr></thead>
          <tbody>{[1, 2, 3, 4, 5].map((period) => <tr key={period}><th scope="row"><span className="demo-period-number">{period}</span><small>tiết</small></th>{days.map((day) => {
            const lesson = lessons.find((item) => item.session === session && item.day === day && item.period === period);
            return <td key={day}>{lesson ? <article className={`demo-timetable-lesson ${lesson.tone || lessonTone(lesson.subject)}`}><span className="demo-lesson-subject">{lesson.subject}</span>{lesson.teacher && <small>{lesson.teacher}</small>}{editing && <button type="button" aria-label={`Xóa ${lesson.subject} thứ ${day}, tiết ${period}`} onClick={() => removeLesson(lesson)}>×</button>}</article> : <span className="demo-empty-slot" aria-label={`Trống, thứ ${day}, tiết ${period}`}>·</span>}</td>;
          })}</tr>)}</tbody>
        </table>
      </div>
    </section>)}
    <p className="demo-timetable-tip"><Icon name="sparkle" size={15} /> Mẹo nhỏ: Bạn có thể tải ảnh thời khóa biểu để tự động điền các tiết học.</p>
  </section>;
}
