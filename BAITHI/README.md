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
- `reminder_worker.py`: tiến trình riêng gửi nhắc hạn bài và nhắc lịch học.
- `backend/schedule_ocr.py`: đọc ảnh thời khóa biểu và suy ra các tiết học.

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

## Tạo thời khóa biểu từ ảnh

Trong ô **Thời khóa biểu** có nút **Tạo từ ảnh**. Bấm nút, chọn ảnh thời khóa biểu, máy sẽ đọc chữ và dựng bảng tiết học để bạn kiểm tra. Chỉ khi bấm **Lưu vào thời khóa biểu** thì dữ liệu mới được ghi, nên có thể sửa trước khi lưu.

Máy đọc ảnh bằng `rapidocr-onnxruntime` và `opencv`, chạy hoàn toàn offline, không cần API key. Cách hoạt động:

1. Nhận ra các cột **Thứ 2** đến **Thứ 7** trên ảnh.
2. Tìm nhãn **SÁNG** / **CHIỀU** để tách hai bảng.
3. Gom chữ theo ô, tách theo dấu `-` thành môn học và giáo viên.
4. Chuẩn hoá tên môn về dạng gọn (ví dụ `NGU' VÃN` → `Ngữ văn`).

Nút này tự ẩn nếu máy chủ chưa cài thư viện đọc ảnh, vì vậy khi deploy cần chạy `pip install -r requirements.txt`.

**Ảnh nên chụp như thế nào:** chụp thẳng, đủ cả bảng, có đủ tiêu đề Thứ 2 đến Thứ 7, chữ rõ và không bị che. Ảnh chụp nghiêng hoặc tối thường đọc sai nhiều ô, nên luôn kiểm tra bảng xem trước.

Kiểm thử trên ảnh mô phỏng: `python tools/make_sample_timetable.py` rồi `python tools/ocr_probe.py`.

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
6. Mở trang học sinh bằng HTTPS, cho phép thông báo của trình duyệt, rồi bấm **Bật thông báo**. Tạo/cập nhật thời khóa biểu để thử push tức thời.

Khai báo các biến trong Render Environment, không commit giá trị bí mật:

- `FCM_ENABLED=true`
- `FIREBASE_PROJECT_ID` (ví dụ `file-85963`)
- `FIREBASE_VAPID_KEY` (Firebase Console → Project Settings → Cloud Messaging → Web Push certificates)
- `FIREBASE_SERVICE_ACCOUNT_JSON` (nội dung JSON service account ghi thành **một dòng**; giữ riêng trong Render Environment, tuyệt đối không commit)
- `PUBLIC_APP_URL` (URL HTTPS của ứng dụng Render)
- `PUSH_CRON_SECRET` (chuỗi ngẫu nhiên dài để bảo vệ endpoint nhắc deadline; đặt cùng giá trị trong GitHub Actions secret)

Sau khi bật push, trình duyệt đăng ký service worker và gắn token FCM với tài khoản học sinh. Khi nhiệm vụ được thêm/hoàn thành hoặc thời khóa biểu thay đổi, thiết bị đã đăng ký sẽ nhận push.

Mỗi nhiệm vụ có ngày và giờ hoàn thành theo giờ Việt Nam. Nhắc hạn được gửi bởi tiến trình riêng `reminder_worker.py`, quét mỗi 60 giây tại các mốc còn 1 ngày, 1 giờ, 10 phút và 5 phút. Người dùng chọn được mốc nhắc, tắt riêng nhắc hạn hoặc nhắc lịch, và đặt giờ yên lặng.

#### Chạy worker nhắc thông báo

```powershell
python reminder_worker.py
```

Trên Render, khai báo thêm một service loại **worker** với lệnh chạy `python reminder_worker.py` (xem `render.yaml`). Đặt `REMINDER_TICK_ENABLED=false` cho service web để tiến trình web không tự gửi nhắc.

Worker và cron GitHub Actions dùng chung một khoá ở tầng dữ liệu (Postgres advisory lock, còn local là SQLite file lock), nên chạy đồng thời nhiều instance vẫn chỉ gửi mỗi mốc nhắc đúng một lần. Endpoint `/api/internal/push-due` cũng dùng chung khoá này và trả về `{"skipped": "locked"}` khi bị bỏ qua. Workflow `.github/workflows/desktop-push-reminders.yml` chạy mỗi phút làm lớp dự phòng.

#### Theo dõi khả năng gửi

Mỗi lần gửi đều được ghi lại trong trạng thái của tài khoản: đã gửi, số thiết bị nhận được, số token hết hạn đã dọn, và lỗi gần nhất. Khi FCM lỗi liên tiếp, worker ghi cảnh báo vào log. Xem nhanh qua:

- `/api/push/status?username=...` — trạng thái đầy đủ kèm lịch sử gửi và danh sách thiết bị.
- `/api/push/health?username=...` — tóm tắt: đã cấu hình FCM chưa, đang lỗi mấy lần liên tiếp.

#### Cài đặt cho người dùng

Cả trang học sinh và trang phụ huynh đều có ô **Cài đặt thông báo**: bật/tắt thông báo, xem số thiết bị đã đăng ký, tắt thông báo trên từng thiết bị, chọn mốc nhắc hạn, đặt giờ yên lặng, và gửi thông báo thử. Tài khoản phụ huynh liên kết với học sinh sẽ nhận thông báo khi học sinh hoàn thành nhiệm vụ (tắt được qua tuỳ chọn **Báo khi học sinh hoàn thành bài**).

#### Kiểm thử trên thiết bị thật

Phần này cần thiết bị thật và Firebase đã cấu hình, không tự động kiểm chứng được:

1. **Android (Chrome)**: bật thông báo, đóng app hẳn, tạo nhiệm vụ hạn sau 5 phút, chờ nhắc. Bấm *Gửi thông báo thử* để kiểm tra nhanh kênh gửi.
2. **iPhone/iPad (Safari)**: phải iOS 16.4 trở lên và cài app vào Màn hình chính. Đóng app hẳn rồi kiểm tra nhắc nền.
3. **Máy tính**: mở app bằng trình duyệt, thử cả khi đang mở tab và khi tab bị ẩn.
4. **Sau khi triển khai lại**: đăng nhập lại ở mỗi thiết bị và bấm *Bật thông báo* một lần, vì token FCM có hạn. Kiểm tra `/api/push/config` trả `ready: true` và log worker không báo lỗi FCM.
5. **Nhiều thiết bị**: đăng ký trên hai máy rồi tắt một máy bằng nút ×, xác nhận máy còn lại vẫn nhận thông báo.

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
OCR_SERVICE_SECRET          = <chuỗi ngẫu nhiên giống nhau ở web và studysync-ocr>
```

OCR thời khóa biểu chạy ở service Render riêng `studysync-ocr`, không chạy trong
Web Service chính. `OCR_SERVICE_URL` được nối tự động từ `render.yaml`; cần đặt
`OCR_SERVICE_SECRET` cùng một giá trị cho hai service. Nhờ vậy lỗi hoặc thiếu bộ
nhớ ở OCR không làm sập website chính.

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

### Bot kiểm duyệt username và lớp

- Username mới phải dài 6–20 ký tự, bắt đầu bằng chữ cái và chỉ dùng chữ không dấu, số hoặc `_`; các tên hệ thống, spam và từ ngữ không phù hợp bị từ chối.
- Tài khoản học sinh chỉ nhận lớp từ `6/1` đến `9/3`. Nếu tài khoản cũ không đạt chính sách, lần đăng nhập tiếp theo sẽ đưa người dùng tới form cập nhật username/họ tên/lớp; lịch học, nhiệm vụ, liên kết phụ huynh và token push được giữ khi đổi username.
- Owner mở **Settings → Bot kiểm duyệt tài khoản** để bật/tắt, quét ngay, xem cảnh báo và đánh dấu đã xem.
- Bot quét ngay khi có đăng ký/đăng nhập hoặc owner yêu cầu. Workflow `.github/workflows/username-policy-scan.yml` quét định kỳ mỗi 15 phút; để bật lịch này, đặt `USERNAME_BOT_CRON_SECRET` trên Render và hai GitHub Actions secrets `USERNAME_BOT_CRON_URL` (URL gốc website) cùng `USERNAME_BOT_CRON_SECRET` (cùng giá trị với Render).
- Gợi ý username dựa trên họ tên, không thu thập năm sinh. Các cảnh báo chỉ hiển thị trong trang quản trị, không gửi username hay thông tin học sinh qua dịch vụ ngoài.

### Quyền riêng tư dữ liệu học sinh

Thời khóa biểu và bài tập/nhiệm vụ được lưu theo username của học sinh. Dashboard học sinh chỉ truy vấn bản ghi của chính mình; dashboard phụ huynh tổng hợp dữ liệu riêng của các học sinh đã liên kết. Các thao tác hoàn thành/cập nhật/xóa cũng ràng buộc theo chủ sở hữu.

Các bản ghi SQLite cũ chưa có chủ sở hữu được giữ lại nhưng không hiển thị cho tài khoản nào. Nếu toàn bộ dữ liệu cũ thực sự thuộc một học sinh cụ thể, có thể đặt `LEGACY_STUDY_OWNER_USERNAME` cho một lần khởi động để gán các hàng cũ chưa có chủ sở hữu. Không đặt biến này nếu DB cũ từng chứa dữ liệu của nhiều người; không thể suy ra chính xác chủ cũ từ schema cũ.
