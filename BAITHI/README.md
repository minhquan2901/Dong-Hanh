# StudySync Web

Ứng dụng theo dõi việc học dành cho phụ huynh. StudySync tập trung vào lịch học, deadline, nhắc việc và tiến độ học tập của học sinh.

## Tính năng

- **Dashboard phụ huynh:** lịch học, deadline, tỷ lệ hoàn thành và tiến độ của học sinh.
- **Theo dõi bài tập:** xem bài đã hoàn thành, bài đang chờ và mức độ ưu tiên.
- **Thông báo:** xem các việc cần phụ huynh quan tâm.

## User flow

1. Mở StudySync và xem Dashboard phụ huynh.
2. Theo dõi lịch học, deadline và tỷ lệ hoàn thành của học sinh.
3. Xem các bài tập chưa hoàn thành để chủ động nhắc nhở.

- `web_app.py`: entry point FastAPI cho portal hợp nhất, login, học sinh và phụ huynh.
- `parent_app.py`: entry point Streamlit cho dashboard phụ huynh độc lập.
- `parent_app.py`: dashboard phụ huynh dùng chung dữ liệu học tập.
- `bus/study_bus.py`: nghiệp vụ lịch học, bài tập và thông báo.
- `database/study_repository.py`: lưu lịch/bài tập trong `data/study_data.json`.

## UI/UX và kiến trúc

Giao diện dùng phong cách Modern Minimalist, nền sáng, điểm nhấn xanh mint/cam và sidebar điều hướng. Dashboard ưu tiên ba thông tin cần quét nhanh: lịch học sắp tới, bài sắp đến hạn và tiến độ tuần. Dữ liệu local dùng JSON để dễ học và chạy nhẹ; khi triển khai lớn có thể chuyển repository sang SQLite hoặc PostgreSQL.

## Chạy trên máy

Cần cài Python 3.10 trở lên.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn web_app:app --reload --port 8000
```

Sau đó mở `http://localhost:8000`.

### Chạy dashboard Streamlit cũ

Nếu muốn chạy riêng dashboard phụ huynh Streamlit:

```powershell
streamlit run parent_app.py --server.port 8501
```

Sau đó mở `http://localhost:8501`.

### Mở trên điện thoại trong cùng Wi-Fi

Chạy Streamlit để lắng nghe trên mạng nội bộ:

```powershell
streamlit run web_app.py --server.address 0.0.0.0 --server.port 8501
```

Trên điện thoại kết nối cùng Wi-Fi với máy tính, mở `http://IP_MAY_TINH:8501`. IP mạng nội bộ có thể xem bằng lệnh `ipconfig` (dòng **IPv4 Address**). Nếu không truy cập được, cho phép Python/Streamlit qua Windows Firewall trên mạng Private. Không dùng `localhost` trên điện thoại vì địa chỉ đó trỏ về chính điện thoại.

Tính năng AI đang tạm tắt. Không cần API key để chạy StudySync.

## Công khai thành link web

1. Tạo repository mới trên GitHub.
2. Đưa toàn bộ project lên GitHub, nhưng bỏ qua `.env`.
3. Truy cập [share.streamlit.io](https://share.streamlit.io), đăng nhập GitHub.
4. Chọn repository, branch và file chính `parent_app.py` nếu deploy bản Streamlit.
5. Bấm **Deploy**. Streamlit sẽ cấp một đường link công khai cho website.

## Push notification trên máy tính

Ứng dụng hỗ trợ Firebase Cloud Messaging (FCM) trên trình duyệt desktop. Push nền cần HTTPS, quyền thông báo, VAPID key và Firebase service account. Điện thoại không được đăng ký nhận push trong giao diện hiện tại.

Khai báo các biến trong môi trường deploy, không commit giá trị bí mật:

- `FCM_ENABLED=true`
- `FIREBASE_PROJECT_ID`
- `FIREBASE_VAPID_KEY` (Firebase Console → Project Settings → Cloud Messaging → Web Push certificates)
- `FIREBASE_SERVICE_ACCOUNT_JSON` (nội dung JSON service account; giữ riêng trong Render Environment)
- `PUBLIC_APP_URL` (URL HTTPS của ứng dụng Render)
- `PUSH_CRON_SECRET` (chuỗi ngẫu nhiên dài để bảo vệ endpoint nhắc deadline)

Sau khi bật push trên máy tính, trình duyệt đăng ký service worker và gắn token FCM với tài khoản học sinh. Khi nhiệm vụ được thêm/hoàn thành hoặc thời khóa biểu thay đổi, máy tính đã đăng ký sẽ nhận push. Workflow `.github/workflows/desktop-push-reminders.yml` chạy hằng ngày lúc 21:00 giờ Việt Nam để gửi nhắc các nhiệm vụ đến hạn ngày hôm sau. Thêm repository secrets `PUSH_CRON_URL` (ví dụ `https://dong-hanh.onrender.com`) và `PUSH_CRON_SECRET` trong GitHub để bật lịch này.

### Giữ tài khoản và dữ liệu sau deploy/restart

Ứng dụng lưu tài khoản trong `users.json`, yêu cầu liên kết trong `link_requests.json`, cùng các dữ liệu ứng dụng trong cùng một thư mục. Mặc định thư mục là `BAITHI/data`; có thể đổi bằng biến môi trường `STUDYSYNC_DATA_DIR`.

Để dữ liệu không mất khi Render deploy lại hoặc thay instance:

1. Sao lưu dữ liệu hiện có từ service (đặc biệt `users.json` và `link_requests.json`) trước khi reset/redeploy hoặc thay storage.
2. Gắn Render Persistent Disk vào service, mount tại `/var/data`.
3. Đặt biến môi trường `STUDYSYNC_DATA_DIR=/var/data/studysync` và đưa bản sao lưu vào thư mục `studysync` trên disk trước khi chạy bản mới.

Khi thư mục persistent mới chưa có một file nhưng file cũ còn trong `BAITHI/data`, ứng dụng sẽ di trú file đó một lần và không ghi đè file đã có trên disk. Nếu hosting đã xóa filesystem cũ trước khi sao lưu, ứng dụng không thể khôi phục dữ liệu đã mất. Tệp JSON lỗi sẽ báo lỗi thay vì bị coi là danh sách rỗng. Đăng xuất không xóa tài khoản. Persistent disk bảo vệ qua deploy/restart; nếu xóa disk hoặc reset/xóa dữ liệu trực tiếp trên disk thì dữ liệu không thể tự khôi phục.

### Tài khoản quản trị owner

Owner đăng nhập tại `/owner`, không tạo qua form đăng ký và không lưu chung với tài khoản học sinh/phụ huynh. Cấu hình các biến sau trong Render Environment; không commit mật khẩu hoặc secret:

- `OWNER_USERNAME`: tên đăng nhập quản trị riêng.
- `OWNER_PASSWORD`: mật khẩu mạnh, tối thiểu 12 ký tự.
- `STUDYSYNC_SESSION_SECRET`: chuỗi ngẫu nhiên tối thiểu 32 ký tự dùng ký token phiên user và owner.

Nếu chưa có biến `STUDYSYNC_SESSION_SECRET`, ứng dụng tạo khóa ở `session_signing_secret.json` trong thư mục dữ liệu. Vì vậy cần cấu hình Persistent Disk và `STUDYSYNC_DATA_DIR` trước khi dùng owner trên hosting. Owner có thể xem thống kê thao tác tính năng thành công và quản lý trạng thái tài khoản; danh sách không trả về mật khẩu.

### Quyền riêng tư dữ liệu học sinh

Thời khóa biểu và bài tập/nhiệm vụ được lưu theo username của học sinh. Dashboard học sinh chỉ truy vấn bản ghi của chính mình; dashboard phụ huynh tổng hợp dữ liệu riêng của các học sinh đã liên kết. Các thao tác hoàn thành/cập nhật/xóa cũng ràng buộc theo chủ sở hữu.

Các bản ghi SQLite cũ chưa có chủ sở hữu được giữ lại nhưng không hiển thị cho tài khoản nào. Nếu toàn bộ dữ liệu cũ thực sự thuộc một học sinh cụ thể, có thể đặt `LEGACY_STUDY_OWNER_USERNAME` cho một lần khởi động để gán các hàng cũ chưa có chủ sở hữu. Không đặt biến này nếu DB cũ từng chứa dữ liệu của nhiều người; không thể suy ra chính xác chủ cũ từ schema cũ.
