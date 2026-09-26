from __future__ import annotations

from datetime import date, datetime
from html import escape

import streamlit as st

from bus.study_bus import StudyBus


st.set_page_config(
    page_title="StudySync | Cổng phụ huynh",
    page_icon="◈",
    layout="wide",
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');
    :root { --ink:#17212b; --muted:#687780; --mint:#d8f3e8; --orange:#f47d5c; --line:#e1e8e4; --blue:#4778a8; }
    html,body,[class*="css"] { font-family:'DM Sans',sans-serif; color:var(--ink); }
    h1,h2,h3 { font-family:'Space Grotesk',sans-serif !important; letter-spacing:-.025em; }
    .stApp { background:#f7faf8; }
    [data-testid="stSidebar"] { background:#17212b; }
    [data-testid="stSidebar"] * { color:#eef6f0 !important; }
    .brand { padding:1rem 0 2rem; }
    .brand-mark { display:inline-flex; width:38px; height:38px; border-radius:12px; background:var(--orange); color:#fff; align-items:center; justify-content:center; font-size:1.35rem; font-weight:700; }
    .brand-name { font:700 1.2rem 'Space Grotesk'; margin-left:.55rem; vertical-align:8px; }
    .eyebrow { color:#dc6d4b; text-transform:uppercase; letter-spacing:.12em; font-size:.7rem; font-weight:700; }
    .hero { background:var(--mint); border-radius:24px; padding:2.2rem 2.6rem; min-height:180px; }
    .hero h1 { font-size:clamp(2rem,4vw,3.5rem); line-height:1; margin:.6rem 0 1rem; }
    .hero p { color:#3d5a50; max-width:650px; font-size:1.03rem; }
    .metric { background:#fff; border:1px solid var(--line); border-radius:16px; padding:1rem 1.15rem; min-height:106px; }
    .metric-label { color:var(--muted); font-size:.82rem; }
    .metric-value { font:700 2rem 'Space Grotesk'; margin-top:.25rem; }
    .metric-note { color:#4a8a6c; font-size:.78rem; }
    .section-title { margin:2rem 0 .8rem; }
    .lesson { border-left:4px solid var(--blue); background:#fff; border-radius:10px; padding:.8rem 1rem; margin:.55rem 0; border-top:1px solid var(--line); border-right:1px solid var(--line); border-bottom:1px solid var(--line); }
    .lesson strong,.task-title { font-family:'Space Grotesk'; }
    .lesson small,.task small { color:var(--muted); }
    .task { background:#fff; border:1px solid var(--line); border-radius:12px; padding:.85rem 1rem; margin:.55rem 0; }
    .priority { color:#d15d3e; font-size:.75rem; font-weight:700; text-transform:uppercase; letter-spacing:.06em; }
    .direction { background:#fff8ed; border:1px solid #f2d6ae; border-radius:12px; padding:1rem 1.1rem; margin:.55rem 0; }
    .direction strong { color:#a6532f; font-family:'Space Grotesk'; }
    @media (max-width: 700px) {
        [data-testid="stSidebar"] { min-width:0 !important; width:0 !important; transform:translateX(-100%); }
        [data-testid="stSidebar"] > div:first-child { width:0 !important; padding:0 !important; }
        [data-testid="stAppViewContainer"] > .main { padding:1rem .75rem 2rem; }
        [data-testid="stMainBlockContainer"] { padding:1rem .75rem 2rem !important; }
        .hero { border-radius:16px; padding:1.35rem 1.1rem; min-height:0; }
        .hero h1 { font-size:2rem; line-height:1.08; }
        .hero p { font-size:.92rem; }
        .metric { min-height:88px; padding:.8rem .75rem; }
        .metric-value { font-size:1.45rem; }
        .metric-label { font-size:.72rem; }
        .metric-note { font-size:.68rem; }
        .section-title { margin:1.35rem 0 .6rem; font-size:1.35rem !important; }
        .lesson,.task,.direction { padding:.75rem .8rem; }
        [data-testid="column"] { width:100% !important; flex:1 1 100% !important; min-width:100% !important; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_study_bus() -> StudyBus:
    return StudyBus()


study = get_study_bus()


def render_lesson(lesson: dict[str, str]) -> None:
    st.markdown(
        f'<div class="lesson"><strong>{escape(str(lesson["subject"]))}</strong><br>'
        f'<small>{escape(str(lesson["day"]))} · {escape(str(lesson["start"]))} · '
        f'Phòng {escape(str(lesson["room"]))} · {escape(str(lesson["lecturer"]))}</small></div>',
        unsafe_allow_html=True,
    )


def render_task(task: dict[str, str | bool]) -> None:
    due_date = datetime.fromisoformat(str(task["due_date"])).date()
    days_left = (due_date - date.today()).days
    due_text = "Hôm nay" if days_left == 0 else f"Còn {days_left} ngày"
    st.markdown(
        f'<div class="task"><div class="task-title">{escape(str(task["title"]))}</div>'
        f'<small>{escape(str(task["subject"]))} · Hạn {due_date.strftime("%d/%m/%Y")} · {due_text}</small>'
        f'<div class="priority">{escape(str(task["priority"]))} · '
        f'{"Đã hoàn thành" if task["completed"] else "Chưa hoàn thành"}</div></div>',
        unsafe_allow_html=True,
    )


def render_direction(stats: dict[str, int | float], assignments: list[dict[str, str | bool]]) -> None:
    pending = [task for task in assignments if not task["completed"]]
    urgent = [task for task in pending if task["priority"] in {"Cao", "Quan trọng"}]
    if not assignments:
        message = "Bắt đầu bằng một mục tiêu nhỏ trong tuần này để tạo nhịp học ổn định."
    elif stats["completion_rate"] >= 80:
        message = "Tiến độ đang rất tốt. Hãy duy trì lịch hiện tại và thử đặt thêm một mục tiêu nâng cao."
    elif urgent:
        message = f"Ưu tiên đồng hành với {len(urgent)} bài quan trọng còn lại, sau đó chia nhỏ thời gian ôn tập mỗi ngày."
    else:
        message = "Nên duy trì một khung giờ học cố định và hoàn thành từng deadline gần nhất trước."
    st.markdown(
        f'<div class="direction"><strong>Định hướng phát triển</strong><br>'
        f'<span>{escape(message)}</span></div>',
        unsafe_allow_html=True,
    )


with st.sidebar:
    st.markdown(
        '<div class="brand"><span class="brand-mark">◈</span>'
        '<span class="brand-name">StudySync</span></div>',
        unsafe_allow_html=True,
    )
    st.markdown("### Cổng phụ huynh")
    st.caption("Theo dõi việc học của con")
    st.divider()
    st.info("Đây là chế độ theo dõi. Dữ liệu được lấy từ hệ thống học tập của học sinh.")


st.markdown(
    '<div class="hero"><div class="eyebrow">Tổng quan học tập</div>'
    '<h1>Theo sát hành trình của con.</h1>'
    '<p>Xem lịch học, deadline và tiến độ hoàn thành trong một màn hình rõ ràng.</p></div>',
    unsafe_allow_html=True,
)

stats = study.stats()
metrics = st.columns(4, gap="small")
metric_values = [
    ("Tổng bài tập", stats["total"], "trong học kỳ"),
    ("Đã hoàn thành", stats["completed"], "bài đã nộp"),
    ("Đang chờ", stats["pending"], "cần theo dõi"),
    ("Tỷ lệ hoàn thành", f'{stats["completion_rate"]}%', "tiến độ hiện tại"),
]
for column, (label, value, note) in zip(metrics, metric_values):
    with column:
        st.markdown(
            f'<div class="metric"><div class="metric-label">{label}</div>'
            f'<div class="metric-value">{value}</div><div class="metric-note">{note}</div></div>',
            unsafe_allow_html=True,
        )

st.markdown('<h2 class="section-title">Tiến độ học tập</h2>', unsafe_allow_html=True)
st.progress(int(stats["completion_rate"]) / 100, text=f'{stats["completion_rate"]}% bài tập đã hoàn thành')

assignments = study.assignments()
st.markdown('<h2 class="section-title">Định hướng phát triển</h2>', unsafe_allow_html=True)
render_direction(stats, assignments)

left, right = st.columns([1.05, .95])
with left:
    st.markdown('<h2 class="section-title">Lịch học</h2>', unsafe_allow_html=True)
    schedule = study.schedule()
    if schedule:
        for lesson in schedule:
            render_lesson(lesson)
    else:
        st.info("Chưa có lịch học.")

with right:
    st.markdown('<h2 class="section-title">Deadline cần quan tâm</h2>', unsafe_allow_html=True)
    if assignments:
        for task in assignments:
            render_task(task)
    else:
        st.info("Chưa có bài tập.")

st.markdown('<h2 class="section-title">Thông báo dành cho phụ huynh</h2>', unsafe_allow_html=True)
pending = [task for task in assignments if not task["completed"]]
if pending:
    st.warning(f"Còn {len(pending)} bài tập chưa hoàn thành.")
else:
    st.success("Hiện không có bài tập nào đang chờ hoàn thành.")
