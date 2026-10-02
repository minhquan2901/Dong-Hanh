# Kế hoạch sửa lỗi và nâng cấp ứng dụng DongHanh

## Mục tiêu

Fix đúng ưu tiên để app DongHanh không còn lộ dữ liệu, không bị bypass quyền, và có thể dùng được ổn định cho học sinh / phụ huynh.

Phạm vi: `DongHanh/` (`app.py`, `Login/index.html`, `Main/index.html`, `ChucnangPH.html`, `Chucnang/*.html`, `tests/`).

Ưu tiên:
- P0: bảo mật và phân quyền
- P1: chức năng hỏng
- P2: trải nghiệm / giao diện
- P3: cleanup và triển khai

---

## Phase 0 — Khóa lỗ hổng bảo mật trước khi sửa chức năng

### 0.1 [P0] Chặn rò rỉ file và path traversal
- Kiểm tra mọi request file tĩnh đều đi qua router chặt chẽ.
- Chỉ cho phép các path hợp lệ: `/`, `/Login/`, `/Main/`, `/Chucnang/*.html`, `/ChucnangPH.html`, `/static/*`.
- Chặn các path có `..`, `%2e%2e`, file `.env`, `.git`, `TaiKhoan/*`, `*.py`, và mọi file ngoài project root.
- Chuyển khỏi `SimpleHTTPRequestHandler` nếu cần.
- Test bắt buộc: `/Main/../TaiKhoan/accounts.json`, `/%2e%2e/TaiKhoan/accounts.json`, `/app.py`, `/.env`.

### 0.2 [P0] Hash mật khẩu, không lưu plaintext
- Dùng `hashlib.pbkdf2_hmac('sha256', ...)` hoặc thuật toán tương đương.
- Lưu dưới dạng hash + salt + thông tin thuật toán.
- Thêm script migrate mật khẩu cũ từ dữ liệu plaintext sang hash.
- Xóa mật khẩu mặc định khỏi repo; không commit file tài khoản nhạy cảm.

### 0.3 [P0] Dùng session thật thay vì localStorage quyết định quyền
- Không được đọc `role` từ `localStorage` để quyết định quyền truy cập.
- Tạo cookie `HttpOnly`/`SameSite`/`Secure` phía server với session cho user login.
- Thêm API:
  - `GET /api/session`
  - `POST /api/logout`
- Tất cả trang đều phải gọi `/api/session` để xác minh trạng thái đăng nhập và role.
- Nếu chưa có session, redirect về `/Login/`.

### 0.4 [P0] Thêm lớp bảo vệ web cơ bản
- CSRF cho mọi `POST/PATCH/DELETE`.
- Giới hạn body size tối đa 16 KB.
- Rate limit đăng nhập theo IP + username (ví dụ 5 lần / 5 phút).
- Kiểm tra `Origin`/`Host` cho API.
- Thêm security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, CSP tối thiểu.

### 0.5 [P1] Không gửi mật khẩu qua URL
- Bỏ form login submit bằng GET.
- Dùng POST với fallback an toàn.
- Không để password xuất hiện trong URL, lịch sử trình duyệt, log server.

---

## Phase 1 — Sửa chức năng hỏng sau khi quyền đã được khóa

### 1.1 [P1] Schedule lưu không nhất quán
- `Main/index.html` và `thoi_khoa_bieu.html` phải dùng chung 1 nguồn dữ liệu.
- Mỗi tiết phải có `id` và `period` rõ ràng.
- Khi xóa tiết, không được đẩy các tiết sau lên sai vị trí.
- Sắp xếp theo giờ / tiết thực tế, không theo index mảng.

### 1.2 [P1] `removeLesson` và render schedule
- Chỉ giữ 1 hàm xóa tiết duy nhất.
- Gắn sự kiện bằng `addEventListener`, không dùng `onclick` inline.
- Render dựa trên `period` thay vì index mảng.
- Nếu tiết đã tồn tại ở cùng ô, báo lỗi rõ ràng.

### 1.3 [P1] Profile lưu role bị mất
- `localStorage` chỉ được dùng cho cache hiển thị, không thay thế dữ liệu server.
- Khi sửa profile, merge object cũ thay vì ghi đè toàn bộ.
- `role` phải luôn giữ nguyên; không được xóa khi cập nhật tên / lớp.

### 1.4 [P1] Default class không thống nhất
- Đưa về một hằng số chung (`DEFAULT_CLASS`) hoặc lấy từ session server.
- Không có trường hợp `7A1` ở một nơi, `8A1` ở nơi khác.

### 1.5 [P1] Ngày trong tuần và dữ liệu tổng quan phải tính theo thời gian thật
- Tạo tuần dựa trên `new Date()`.
- Đánh dấu `today` theo ngày thực.
- Tính số liệu từ `schedule.table` và `assignments.table`, không hardcode.

### 1.6 [P1] Bài tập phải lưu trạng thái
- Lưu trạng thái hoàn thành của bài tập vào local store / backend store.
- Đồng bộ giữa học sinh và phụ huynh nếu cùng dữ liệu.
- F5 không làm mất trạng thái tiến độ.

### 1.7 [P1] Chặn truy cập khi chưa đăng nhập
- Trang `Main`, `ChucnangPH.html`, `thoi_khoa_bieu.html` phải kiểm tra session.
- Nếu thiếu session, redirect về `/Login/`.

### 1.8 [P2] `registerAccount()` phải có error handling đầy đủ
- Dùng `try/catch/finally`.
- Kiểm tra `response.ok`.
- Thông báo lỗi tiếng Việt rõ ràng.
- Khóa nút gửi trong lúc yêu cầu chạy.

---

## Phase 2 — Giao diện & trải nghiệm

### 2.1 [P2] Modal và form
- Cho phép đóng bằng Esc và click ngoài modal.
- Khóa scroll khi modal mở.
- Focus trap nếu cần.

### 2.2 [P2] Tách CSS / JS chung
- Tạo `static/theme.css` hoặc file CSS dùng chung cho app.
- Không để các block `<style>` lặp lại và override nhau.
- Dùng font-stack thống nhất.

### 2.3 [P2] Ẩn nút chết
- Các nút như Google / Quên mật khẩu mà chưa triển khai cần ẩn hoặc thay bằng trạng thái rõ ràng.
- Không để UI có tính năng “bấm vô không có gì”.

### 2.4 [P3] Thêm empty state và error handling
- Trang/trạng thái rỗng khi chưa có dữ liệu.
- Hiển thị thông báo lỗi khi fetch thất bại.
- Thêm 404 error page thân thiện.

---

## Phase 3 — Backend / dữ liệu / hệ thống

### 3.1 [P1] Dữ liệu tài khoản phải được đồng bộ và an toàn
- Chỉ giữ 1 nguồn dữ liệu tài khoản dạng chuẩn hóa.
- Không để `role` lẫn lộn giữa `user`/`student`/`parent`.
- Dùng lock khi đọc/ghi file để tránh race condition.

### 3.2 [P1] Validate dữ liệu đầu vào
- Username: chữ thường, số, dấu chấm/gạch dưới/gạch nối, độ dài hợp lý.
- Mật khẩu: dài tối thiểu, có chữ và số.
- `display_name`: giới hạn chiều dài hợp lý, trim whitespace.

### 3.3 [P2] Quản lý quyền cha-con / học sinh
- Parent phải gắn với con hoặc lớp cụ thể.
- API dữ liệu phải kiểm tra quyền truy cập theo role.
- Không cho parent xem dữ liệu học sinh khác.

### 3.4 [P3] Logging và triển khai
- Log request / login failed / error.
- Chốt hướng deploy rõ ràng: local-only hay có service deploy thật.
- Nếu deploy qua Render, cần storage bền vững hoặc dùng DB ngoài.

---

## Phase 4 — Test & xác minh

Thêm test cho các trường hợp sau:
1. Static exposure / path traversal
2. Đăng nhập sai mật khẩu / rate limit
3. Session và quyền truy cập
4. Profile giữ nguyên `role`
5. Schedule period / xóa tiết / render đúng
6. Persistence tài khoản

Sau khi sửa, chạy smoke test bằng trình duyệt headless cho các luồng chính:
- học sinh login
- phụ huynh login
- sửa profile
- thêm/xóa tiết
- logout
- mobile 375px

---

## Thứ tự ưu tiên thực thi

1. P0: rò rỉ file + session + hash mật khẩu
2. P0: CSRF + rate limit + headers
3. P1: schedule + profile + đăng nhập + session guard
4. P1: assignments + week summary + role checks
5. P2: UI cleanup / modal / CSS / empty states
6. P3: logging / cleanup / deploy clarity
7. Test + smoke verification

## Rủi ro cần lưu ý

- Đổi session và role phải đồng bộ cùng lúc trên các trang; nếu không, người dùng sẽ bị mất quyền ngay.
- Khi đổi định dạng mật khẩu và tài khoản, cần backup trước và migrate dữ liệu cũ.
- Không làm đồng thời quá nhiều thay đổi API mà không giữ backward compatibility.

## Ngoài phạm vi

Dự án `BAITHI/` là project riêng, có kiến trúc khác. Kế hoạch này chỉ tập trung vào `DongHanh/` và không audit `BAITHI` trừ khi được yêu cầu.
