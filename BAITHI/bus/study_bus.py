from __future__ import annotations

from datetime import date, datetime, timedelta

from database.study_repository import StudyRepository


class StudyBus:
    """Nghiệp vụ lịch học, bài tập, nhắc hạn và thống kê."""

    def __init__(self) -> None:
        self.repository = StudyRepository()

    def schedule(self) -> list[dict[str, str]]:
        return self.repository.get_schedule()

    def upsert_schedule_slot(
        self, session: str, day: str, period: int, subject: str, lecturer: str
    ) -> dict[str, str | int]:
        if session not in {"morning", "afternoon"}:
            raise ValueError("Buổi học không hợp lệ.")
        if day not in {"2", "3", "4", "5", "6", "7"}:
            raise ValueError("Thứ học không hợp lệ.")
        if period not in range(1, 6):
            raise ValueError("Tiết học phải từ 1 đến 5.")
        if not subject.strip():
            raise ValueError("Tên môn học không được để trống.")
        return self.repository.upsert_schedule_slot(
            session, day, period, subject.strip(), lecturer.strip()
        )

    def upsert_schedule_slots(self, slots: list[dict[str, str | int]]) -> list[dict[str, str | int]]:
        normalized = []
        for slot in slots:
            normalized.append({
                "session": str(slot.get("session", "morning")).strip(),
                "day": str(slot.get("day", "2")).strip(),
                "period": int(slot.get("period", 1)),
                "subject": str(slot.get("subject", "")).strip(),
                "lecturer": str(slot.get("lecturer", "")).strip(),
            })
        return self.repository.upsert_schedule_slots(normalized)

    def delete_schedule_slot(self, session: str, day: str, period: int) -> bool:
        return self.repository.delete_schedule_slot(session, day, period)

    def assignments(self) -> list[dict[str, str | bool]]:
        return self.repository.get_assignments()

    def add_schedule(
        self,
        subject: str,
        day: str,
        start: str,
        room: str,
        lecturer: str,
        reminder_minutes: int,
    ) -> None:
        if not subject.strip():
            raise ValueError("Tên môn học không được để trống.")
        self.repository.add_schedule(
            subject.strip(), day, start, room.strip(), lecturer.strip(), reminder_minutes
        )

    def notifications(self) -> list[dict[str, str]]:
        alerts = []
        for lesson in self.schedule():
            reminder = lesson.get("reminder_minutes", 30)
            alerts.append(
                {
                    "title": f"Nhắc lịch: {lesson['subject']}",
                    "detail": f"{lesson['day']} lúc {lesson['start']} · Phòng {lesson['room']} · nhắc trước {reminder} phút",
                }
            )
        for task in self.due_soon():
            alerts.append(
                {
                    "title": f"Deadline: {task['title']}",
                    "detail": f"{task['subject']} · hạn {task['due_date']} · ưu tiên {task['priority']}",
                }
            )
        return alerts

    def add_assignment(self, title: str, subject: str, due_date: date, priority: str) -> dict[str, str | bool]:
        if not title.strip() or not subject.strip():
            raise ValueError("Tên bài tập và môn học không được để trống.")
        if priority not in {"Thấp", "Trung bình", "Cao", "Quan trọng"}:
            raise ValueError("Mức ưu tiên không hợp lệ.")
        return self.repository.add_assignment(title.strip(), subject.strip(), due_date.isoformat(), priority)

    def set_completed(self, assignment_id: str, completed: bool) -> bool:
        return self.repository.set_assignment_completed(assignment_id, completed)

    def delete_assignment(self, assignment_id: str) -> bool:
        return self.repository.delete_assignment(assignment_id)

    def due_soon(self, days: int = 7) -> list[dict[str, str | bool]]:
        today = date.today()
        limit = today + timedelta(days=days)
        return [
            item for item in self.assignments()
            if not item["completed"] and today <= datetime.fromisoformat(str(item["due_date"])).date() <= limit
        ]

    def stats(self) -> dict[str, int | float]:
        tasks = self.assignments()
        total = len(tasks)
        completed = sum(1 for task in tasks if task["completed"])
        return {
            "total": total,
            "completed": completed,
            "pending": total - completed,
            "completion_rate": round(completed / total * 100) if total else 0,
        }
