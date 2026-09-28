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

## Push notification trên máy tính và điện thoại

Ứng dụng hỗ trợ Firebase Cloud Messaging (FCM) trên máy tính và điện thoại. Android có thể bật push từ trình duyệt; cài PWA để mở như app. Trên iPhone/iPad, push yêu cầu iOS/iPadOS 16.4 trở lên, Safari và app đã được thêm vào Màn hình chính. Push nền cần HTTPS, quyền thông báo, VAPID key và Firebase service account.

Trên Android có thể bật thông báo trực tiếp trong trình duyệt; cài PWA là tùy chọn để mở app riêng. Riêng iPhone/iPad cần cài app vào Màn hình chính trước khi đăng ký push:

- **Android (Chrome)**: menu ⋮ → *Cài app*, sau đó mở lại từ màn hình chính.
- **iPhone (Safari)**: nút Chia sẻ → *Thêm vào Màn hình chính*, sau đó mở lại từ màn hình chính. Cần iOS 16.4 trở lên và chỉ Safari hỗ trợ.

#### Bật Firebase và cấu hình Render

1. Trong Firebase Console, mở project `file-85963` (hoặc project tương ứng với cấu hình client trong `firebase-notifications.js` và `firebase-messaging-sw.js`). Đảm bảo Firebase Cloud Messaging API (V1) đang bật.
2. Vào **Project settings → Cloud Messaging → Web Push certificates** và chọn **Generate key pair**. Sao chép public key VAPID.
3. Tạo Firebase service account JSON trong **Project settings → Service accounts → Generate new private key**. Giữ file này riêng tư.
4. Trên Render, mở service → **Environment → Add Environment Variable** và thêm các biến bên dưới. Dán toàn bộ JSON service account vào một dòng cho `FIREBASE_SERVICE_ACCOUNT_JSON`.
5. Bấm **Save, rebuild, and deploy** (hoặc lưu rồi manual deploy). Mở `/api/push/config`; khi cấu hình đúng, kết quả phải có `ready: true` và `vapid_key` khác rỗng.
6. Mở trang học sinh bằng HTTPS, cho phép thông báo của trình duyệt, rồi bấm **Bật thông báo**. Kiểm tra thông báo bằng cách tạo/cập nhật tác vụ hoặc thời khóa biểu.

Khai báo các biến trong Render Environment, không commit giá trị bí mật:

- `FCM_ENABLED=true`
- `FIREBASE_PROJECT_ID` (ví dụ `file-85963`)
- `FIREBASE_VAPID_KEY` (Firebase Console → Project Settings → Cloud Messaging → Web Push certificates)
- `FIREBASE_SERVICE_ACCOUNT_JSON` (nội dung JSON service account ghi thành **một dòng**; giữ riêng trong Render Environment, tuyệt đối không commit)
- `PUBLIC_APP_URL` (URL HTTPS của ứng dụng Render)
- `PUSH_CRON_SECRET` (chuỗi ngẫu nhiên dài để bảo vệ endpoint nhắc deadline)

Sau khi bật push, trình duyệt đăng ký service worker và gắn token FCM với tài khoản học sinh. Khi nhiệm vụ được thêm/hoàn thành hoặc thời khóa biểu thay đổi, thiết bị đã đăng ký sẽ nhận push. Workflow `.github/workflows/desktop-push-reminders.yml` chạy hằng ngày lúc 21:00 giờ Việt Nam để gửi nhắc các nhiệm vụ đến hạn ngày hôm sau. Thêm repository secrets `PUSH_CRON_URL` (ví dụ `https://dong-hanh.onrender.com`) và `PUSH_CRON_SECRET` trong GitHub để bật lịch này.

### Giữ tài khoản và dữ liệu sau deploy/restart

Render gói **Free** không có persistent disk: mỗi lần deploy là một instance mới, mọi file ghi trong thư mục mã nguồn đều bị mất. Nếu để tài khoản trong `BAITHI/data/users.json` thì mỗi lần deploy tài khoản sẽ mất sạch.

Giải pháp là lưu dữ liệu vào **Neon Postgres** (gói free, 0.5 GB, không cần thẻ tín dụng). Ứng dụng chọn nguồn lưu trữ theo biến môi trường `STUDYSYNC_DATABASE_URL`:

- Có biến này → đọc/ghi trên Postgres.
- Không có → dùng file JSON như cũ, để chạy local và chạy test.

Nhờ vậy cùng một mã nguồn chạy được cả hai nơi mà không cần đổi cấu hình.

#### 1. Tạo database trên Neon

1. Đăng ký tài khoản miễn phí tại [neon.com](https://neon.com).
2. Tạo project, chọn region gần Render nhất, chọn gói Free.
3. Neon tự tạo database `neondb` và schema `public`.

#### 2. Lấy chuỗi kết nối

Vào **Connection Details** trong Neon Console, chọn driver **Python**, sao chép chuỗi kết nối. Nó có dạng:

```
postgresql://ten_user:mat_khau@ep-xxx-pooler.region.aws.neon.tech/neondb?sslmode=require
```

Đặt chuỗi này vào biến môi trường `STUDYSYNC_DATABASE_URL` trên Render.

#### 3. Chuyển dữ liệu cũ lên Neon

Chạy **một lần duy nhất**, trước khi deploy bản dùng database:

```powershell
$env:STUDYSYNC_DATABASE_URL = "postgresql://...sslmode=require"
.\.venv\Scripts\python.exe migrate_to_postgres.py
```

Script tạo bảng nếu chưa có, rồi tải lên tài khoản, yêu cầu liên kết, hòm thư góp ý, thống kê sử dụng, thời khóa biểu và bài tập. Script **không ghi đè** dữ liệu đang có trên Neon, nên chạy lại cũng an toàn.

#### 4. Cấu hình Render

Trong Render Dashboard → service → **Settings → Environment**, thêm:

```
STUDYSYNC_DATABASE_URL      = <chuỗi kết nối Neon>
STUDYSYNC_SESSION_SECRET    = <chuỗi ngẫu nhiên từ 32 ký tự trở lên>
STUDYSYNC_OWNER_SECRET      = <chuỗi ngẫu nhiên từ 32 ký tự trở lên>
OWNER_USERNAME              = <tên đăng nhập quản trị>
OWNER_PASSWORD              = <mật khẩu quản trị>
```

`STUDYSYNC_SESSION_SECRET` phải cố định. Nếu để ứng dụng tự sinh khóa ở `session_signing_secret.json` trong thư mục dữ liệu, thì trên gói Free khóa đó mất sau mỗi lần deploy và mọi phiên đăng nhập đang mở đều bị đăng xuất.

#### 5. Kiểm tra sau khi deploy

Mở `/health/data`. Kết quả đúng sẽ có:

```json
{"backend": "postgres", "user_count": 12, "has_session_secret": true}
```

Nếu `backend` vẫn là `file` hoặc `user_count` bằng 0 thì `STUDYSYNC_DATABASE_URL` chưa được đặt đúng, hoặc script migrate chưa chạy.

Tệp JSON lỗi vẫn báo lỗi thay vì bị coi là danh sách rỗng, và đăng xuất không xóa tài khoản.

### Tài khoản quản trị owner

Owner đăng nhập tại `/owner`, không tạo qua form đăng ký và không lưu chung với tài khoản học sinh/phụ huynh. Cấu hình các biến sau trong Render Environment; không commit mật khẩu hoặc secret:

- `OWNER_USERNAME`: tên đăng nhập quản trị riêng.
- `OWNER_PASSWORD`: mật khẩu mạnh, tối thiểu 12 ký tự.
- `STUDYSYNC_SESSION_SECRET`: chuỗi ngẫu nhiên tối thiểu 32 ký tự dùng ký token phiên user và owner.

Nếu chưa có biến `STUDYSYNC_SESSION_SECRET`, ứng dụng tạo khóa ở `session_signing_secret.json` trong thư mục dữ liệu. Vì vậy cần đặt biến này khi chạy trên Render, nếu không mọi lần deploy sẽ sinh khóa mới và đăng xuất toàn bộ người dùng. Owner có thể xem thống kê thao tác tính năng thành công và quản lý trạng thái tài khoản; danh sách không trả về mật khẩu.

Render tự động deploy lại mỗi khi có commit mới đẩy lên branch đang nối với service. Không cần cấu hình gì thêm trong code. Quy trình thực tế:

1. Render Dashboard → service của bạn → **Settings**.
2. Kiểm tra **Connected Branch** là `main` và repository `minhquan2901/Dong-Hanh`.
3. Giữ **Auto-Deploy** bật (mặc định). Mỗi lần `git push origin main`, Render pull code mới, cài lại `requirements.txt` và khởi động lại ứng dụng.
4. Theo dõi tiến trình ở tab **Events**; trạng thái khoẻ ở `/health`.

Nếu bạn muốn kiểm soát thủ công, tắt Auto-Deploy rồi dùng **Deploy Hook**:

1. Render Dashboard → service → **Settings → Deploy Hook** → **Create Deploy Hook**, sao chép URL.
2. Thêm URL đó vào repository secrets trên GitHub với tên `RENDER_DEPLOY_HOOK_URL` (Settings → Secrets and variables → Actions).
3. Workflow `.github/workflows/render-deploy.yml` sẽ gọi hook mỗi khi có push vào `main`.

Lưu ý: biến môi trường và Persistent Disk được giữ nguyên qua các lần deploy; chỉ code mới được thay thế. Deploy lại khoảng 1–3 phút, trong lúc đó web có thể báo lỗi tạm thời. Nếu deploy thất bại, Render rollback về bản build trước đó nên web vẫn chạy.

### Quản lý tài khoản, hồ sơ và hòm thư góp ý

- Owner đăng nhập tại `/owner`: xem thống kê, **Khóa / Mở khóa** tài khoản, **Sửa** họ tên và lớp, và đọc hòm thư báo lỗi/góp ý của người dùng.
- Người dùng vào `/account` để cập nhật họ tên, lớp, avatar và đặt lại mật khẩu. Nút tròn góc phải mở hộp thoại báo lỗi / góp ý.
- Đổi mật khẩu hoặc bị khóa sẽ làm mọi phiên đang đăng nhập mất hiệu lực ngay (token phiên mang kèm `session_version`).

### Quyền riêng tư dữ liệu học sinh

Thời khóa biểu và bài tập/nhiệm vụ được lưu theo username của học sinh. Dashboard học sinh chỉ truy vấn bản ghi của chính mình; dashboard phụ huynh tổng hợp dữ liệu riêng của các học sinh đã liên kết. Các thao tác hoàn thành/cập nhật/xóa cũng ràng buộc theo chủ sở hữu.

Các bản ghi SQLite cũ chưa có chủ sở hữu được giữ lại nhưng không hiển thị cho tài khoản nào. Nếu toàn bộ dữ liệu cũ thực sự thuộc một học sinh cụ thể, có thể đặt `LEGACY_STUDY_OWNER_USERNAME` cho một lần khởi động để gán các hàng cũ chưa có chủ sở hữu. Không đặt biến này nếu DB cũ từng chứa dữ liệu của nhiều người; không thể suy ra chính xác chủ cũ từ schema cũ.
