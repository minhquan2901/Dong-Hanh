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
- `backend/timetable_ai.py`: gửi ảnh thời khóa biểu tới Gemini Flash và kiểm tra JSON trả về.

## UI/UX và kiến trúc

Giao diện dùng phong cách Modern Minimalist, nền sáng, điểm nhấn xanh mint/cam và sidebar điều hướng. Dashboard ưu tiên ba thông tin cần quét nhanh: lịch học sắp tới, bài sắp đến hạn và tiến độ tuần. Dữ liệu local dùng JSON để dễ học và chạy nhẹ; khi triển khai lớn có thể chuyển repository sang SQLite hoặc PostgreSQL.

### Frontend React trên Vercel và Render, API dùng chung

Frontend React + Vite nằm trong `web-client/` và được phục vụ như static site trên cả Vercel lẫn Render. Hai địa chỉ dùng cùng source/build, cùng gọi FastAPI backend và Neon Postgres trên Render, nên giao diện và dữ liệu nhất quán. Backend và reminder worker tiếp tục chạy trên Render. Frontend cung cấp đăng nhập/đăng ký, dashboard học sinh/phụ huynh, bài tập, quản lý hồ sơ, thời khóa biểu, thông báo/push/PWA và quản trị owner. Không chuyển secrets/database sang frontend.

**Phân vai:** Vercel và Render đều phục vụ frontend tĩnh; Render đồng thời cung cấp API HTTPS, tác vụ nền và kết nối Neon. Chọn một domain chính để chia sẻ cho người dùng và giữ `PUBLIC_APP_URL` trỏ về domain đó; các domain còn lại vẫn dùng được nhưng thông báo/push có thể mở domain chính. Mỗi domain có service worker/PWA riêng. Không deploy secrets/database lên frontend và không cache API chứa dữ liệu tài khoản.

#### Chạy frontend local

Mở hai terminal trong `BAITHI`. Terminal thứ nhất chạy backend:

```powershell
python -m uvicorn web_app:app --reload --port 8000
```

Terminal thứ hai chạy frontend:

```powershell
cd web-client
npm install
npm run dev
```

Mở URL Vite in ra (thường là `http://localhost:5173`). Proxy dev chuyển `/api` sang `http://127.0.0.1:8000`.

#### Checklist trước khi chuyển đổi

- Kiểm tra trạng thái Git và commit sẽ deploy: `git status`, `git log -1 --oneline`, `git fetch origin`. Có thể sao lưu toàn bộ refs trước khi thay đổi bằng `git bundle create ..\dong-hanh-backup.bundle --all` (cất bundle bên ngoài repository, không commit). Xác nhận có thể truy cập lại repository từ GitHub.
- Sao lưu/kiểm tra khả năng khôi phục Neon theo gói đang dùng; xác nhận `/health` của Render trả HTTP 200 và tài khoản/dữ liệu hiện có vẫn đọc được. Không cần migrate database cho lần chuyển frontend này.
- Ghi nhận các biến môi trường, nhưng **không** đưa giá trị secret vào Git hoặc Vercel:

| Nền tảng | Biến | Giá trị/phạm vi |
|---|---|---|
| Vercel và Render Static Site | `VITE_API_BASE_URL` | Cùng đặt URL gốc HTTPS của Render Web Service, ví dụ `https://dong-hanh.onrender.com`, không có `/` cuối. Đây là cấu hình công khai được đóng gói vào JavaScript lúc build. |
| Render Web Service | `STUDYSYNC_CORS_ORIGINS` | Origin frontend Vercel, Render Static Site và custom domain nếu có; phân tách bằng dấu phẩy, không có path/dấu `/` cuối. |
| Render Web Service + Worker | `PUBLIC_APP_URL` | URL frontend HTTPS chính (khuyến nghị Vercel hoặc custom domain) để liên kết và push mở giao diện tại domain thống nhất. |
| Render | `STUDYSYNC_DATABASE_URL`, `STUDYSYNC_SESSION_SECRET`, Firebase service account/VAPID private material, Gemini key, cron secrets | Giữ nguyên ở Render; không sao chép sang Vercel. |

Trong CORS, thêm từng origin dùng thực tế, ví dụ `https://your-project.vercel.app,https://donghanhhoctap.com,https://www.donghanhhoctap.com`. Không thêm đường dẫn và không dùng wildcard `*`/`*.vercel.app`. Với Preview Deployment, chỉ thêm origin cụ thể cần kiểm thử rồi gỡ khi không còn dùng.

#### Danh mục tài liệu học tập

- Trang **Tài liệu PDF** dùng `web-client/src/materialCatalog.json` để lọc theo môn, lớp 6–9 và tập. PDF mở từ Google Drive; file không được đóng gói vào Vercel.
- Tải PDF lên Google Drive. Với từng file, chọn **Share → General access → Anyone with the link → Viewer**, sau đó sao chép đường dẫn chia sẻ.
- Điền link chia sẻ vào thuộc tính `sourceUrl` của đúng tài liệu trong `web-client/src/materialCatalog.json`. Trang sẽ bật nút **Mở trên Drive** khi có URL.
- Link chia sẻ công khai cho phép bất kỳ ai có link xem file; chỉ bật chia sẻ với những PDF bạn có quyền phân phối. Google Drive có thể tạm giới hạn lượt truy cập/tải cao bất thường; Google không công bố mức người dùng tải đồng thời được đảm bảo.

#### Triển khai frontend lên Vercel

1. Import repository hiện có vào Vercel; không cần tách repository. Chọn **Root Directory** `BAITHI/web-client`.
2. Chọn Framework Preset **Vite**, Node.js **22.x**, Build Command `npm run build`, Output Directory `dist`. Giữ Install Command mặc định theo lockfile.
3. Thêm `VITE_API_BASE_URL` trong Vercel → Project → Settings → Environment Variables cho **Production** và **Preview** nếu cần. Cấu hình được nhúng lúc build nên phải redeploy sau khi sửa. Nếu bỏ sót, frontend hiện lỗi cấu hình rõ ràng thay vì âm thầm gửi request về domain Vercel.
4. Cập nhật `STUDYSYNC_CORS_ORIGINS` trên Render Web Service với origin Vercel Preview chính xác, lưu và deploy backend; kiểm tra `/health` và preflight/các request API trong DevTools → Network.
5. Mở Preview URL và kiểm thử checklist ở phần dưới. Sau khi đạt mới gắn domain chính thức, cập nhật CORS + `PUBLIC_APP_URL` thành domain đó, rồi redeploy Render và Vercel.

#### Triển khai cùng frontend lên Render

1. Blueprint tại `render.yaml` khai báo static site `studysync-web`; Root Directory `BAITHI/web-client`, Build Command `npm ci && npm run build`, Publish Directory `dist`, và rewrite các route SPA về `index.html`.
2. Khi tạo mới Blueprint trên Render, nhập `VITE_API_BASE_URL` là URL HTTPS của Web Service `dong-hanh` (không có dấu `/` cuối). Nếu Blueprint đã tồn tại, `sync: false` không tự thêm biến khi sync lại; vào Render Dashboard → Static Site `studysync-web` → Environment, thêm biến này thủ công rồi redeploy.
3. Sau khi site deploy lần đầu, lấy chính xác URL `*.onrender.com` do Render cấp. Thêm origin đó vào `STUDYSYNC_CORS_ORIGINS` của Web Service `dong-hanh` cùng origin Vercel; lưu và redeploy backend. Giữ `PUBLIC_APP_URL` trỏ về domain frontend chính đã chọn.
4. Kiểm thử đăng nhập, API, tải lại trực tiếp các route như `/student/materials` và `/student/schedule`, rồi xác nhận filter tài liệu và các chức năng cập nhật vẫn hoạt động. Mỗi push lên nhánh deploy sẽ build lại Render Static Site và Vercel theo cấu hình auto-deploy của từng service.

#### Đo độ trễ thời khóa biểu

- Mở DevTools → Console và so sánh các dòng `[StudySync API timing]` của `GET /api/schedule/slots`: `requestNumber: 1` là lần gọi đầu trong tab; `headersMs` đo thời gian tới khi nhận response headers; `totalMs` gồm cả tải/đọc JSON. Yêu cầu từ 1 giây trở lên được ghi cảnh báo. Không ghi username hay token vào phép đo.
- Trang thời khóa biểu dùng endpoint chỉ trả danh sách tiết, không tải lại toàn bộ dashboard. Kiểm tra ảnh chỉ được gọi khi người dùng chọn ảnh.
- Lịch xem gần nhất được lưu trong trình duyệt theo username để hiện ngay khi mở trang; ứng dụng vẫn tải dữ liệu mới từ backend. Cache chỉ được thay bằng response thành công và API lịch được đánh dấu `private, no-store`; nếu backend chưa phản hồi, giao diện báo đang dùng bản cũ. Cache này không đồng bộ giữa thiết bị và không bảo đảm dữ liệu mới luôn về dưới 1 giây khi Render Free đang ngủ.
- Dashboard học sinh/phụ huynh và danh sách tiết được cache trong `sessionStorage` theo tài khoản để chuyển trang trong cùng phiên không gọi lại API liên tục. Nút **Làm mới** buộc đồng bộ với máy chủ; thao tác ghi thành công tự xóa cache liên quan. Cache hết hạn sau 5 phút, chỉ tồn tại trong phiên tab và không thay thế dữ liệu server.
- Hoàn thành/xóa/thêm nhiệm vụ và thêm/xóa tiết được cập nhật lạc quan trên giao diện trước khi request ghi hoàn tất; nếu server từ chối, trạng thái sẽ được hoàn tác và lỗi hiển thị. SQLite local đã có index cho chủ sở hữu + thời khóa biểu, chủ sở hữu + hạn bài tập và nhắc hạn chưa hoàn thành.
- Các lần ghi lịch/bài tập tiếp tục chạy background task cho thống kê và push sau khi response đã gửi; không chuyển gửi thông báo vào luồng cập nhật giao diện.
- So sánh lần đầu sau thời gian không dùng với lần tải tiếp theo trong Network. Nếu chỉ lần đầu chậm, đó thường là cold start của gói Free; nếu mọi lần đều chậm, xem `headersMs` để điều tra backend/database. Đảm bảo `VITE_API_BASE_URL` là URL Render thật và origin frontend thực tế có trong `STUDYSYNC_CORS_ORIGINS`.

#### Domain và chuyển đổi không gián đoạn

1. Thêm `donghanhhoctap.com` (và tùy chọn `www.donghanhhoctap.com`) trong Vercel → Project → Settings → Domains. Trước ngày chuyển, giảm TTL bản ghi DNS hiện tại nếu nhà cung cấp cho phép.
2. Cấu hình DNS theo **đúng giá trị Vercel hiển thị cho domain của project**: domain gốc (`@`) thường dùng A record; `www` thường dùng CNAME. Không xóa/đổi domain `*.onrender.com` của backend và không tự dùng IP mẫu nếu Vercel đưa giá trị khác.
3. Giữ backend Render cũ chạy trong suốt quá trình. Preview trên Vercel dùng cùng backend và dữ liệu hiện tại; sau khi kiểm thử đăng nhập, role học sinh/phụ huynh/owner, bài tập, lịch, push và mobile, mới đổi DNS frontend.
4. **Rollback:** nếu frontend mới có lỗi, trỏ DNS về đích frontend Render cũ hoặc rollback deployment Vercel trong Dashboard; giữ nguyên Render API và Neon. Khôi phục bản ghi DNS đã ghi lại, chờ TTL cập nhật, rồi điều tra trên Preview trước khi thử lại. Session trên hai domain không chia sẻ nhau nên người dùng có thể cần đăng nhập lại.
5. Thông báo bảo trì chỉ cần nếu có thời gian gián đoạn thực tế: “StudySync đang cập nhật giao diện; dữ liệu học tập được giữ nguyên. Nếu chưa vào được, vui lòng thử lại sau ít phút.” Với quy trình Preview → đổi DNS, không cần khóa ghi dữ liệu hoặc lên lịch bảo trì.

#### Kiểm thử giữ nguyên tính năng (Feature Parity)

| Nhóm | Kiểm tra trên domain Vercel |
|---|---|
| Tài khoản | Đăng ký, đăng nhập/đăng xuất, khôi phục session sau refresh, hết hạn JWT, PIN; thử từng role học sinh, phụ huynh và owner. |
| Học tập | Đọc/tạo/sửa/hoàn thành/xóa nhiệm vụ; lịch học và nhập ảnh; dữ liệu vẫn còn sau khi reload và đăng nhập lại. |
| Phụ huynh | Gửi/yêu cầu liên kết, chấp nhận/từ chối, xem và cập nhật hồ sơ học sinh theo đúng quyền. |
| API & bảo mật | DevTools không có lỗi CORS/4xx/5xx bất thường; request đi tới host Render; token chỉ gửi qua HTTPS; secret không xuất hiện trong bundle. |
| Thông báo | Cấu hình push, đăng ký/gỡ thiết bị, thử thông báo và kiểm tra click mở domain Vercel; xác nhận Firebase đã cho phép domain. |
| Tương thích | Kiểm tra màn hình đăng nhập, dashboard, lịch và biểu mẫu ở mobile (360px), tablet và desktop; kiểm tra thao tác bàn phím và trạng thái lỗi/loading. |
| Hiệu năng & triển khai | Đo tải trang lần đầu và sau cache; kiểm tra `/health` khi backend vừa ngủ; mở trực tiếp deep link `/owner`, `/account`, `/student/schedule`, `/notifications`. |

#### Tối ưu vận hành sau khi chuyển

- Vercel phục vụ HTML, JS/CSS đã hash và ảnh tĩnh qua CDN. Tài liệu công khai có thể cache theo URL/version; không bật cache dùng chung cho API cá nhân hóa, hồ sơ, JWT hoặc response phụ thuộc tài khoản. Ảnh nội dung lớn nên dùng storage/CDN riêng và lazy-load.
- Free Web Service của Render có thể cold start. UptimeRobot/Cron-job.org ping `https://<render-service>.onrender.com/health` mỗi 10–14 phút là **best effort**, không bảo đảm uptime và không thay thế chính sách của Render. Nếu cần phản hồi ổn định cho học sinh, chọn gói Render always-on; đừng ping endpoint có tác dụng phụ hoặc endpoint dữ liệu.
- Theo dõi Render logs, `/health`, tỷ lệ lỗi API và thời gian phản hồi; theo dõi Vercel deployment/build. Chỉ đưa thay đổi CORS/domain vào production sau khi Preview được xác nhận.

#### Lộ trình tính năng

1. **Ngắn hạn:** đo cold start và API latency; cân nhắc Render always-on, giám sát uptime, cache asset công khai/versioned, tối ưu ảnh và kiểm tra responsive/accessibility.
2. **Trung hạn:** streak/badge có giới hạn hợp lý, biểu đồ tiến độ theo tuần, nhắc lịch có thể tùy chỉnh, ghi chú và flashcard gắn với môn học; lưu dữ liệu qua API và cho người dùng kiểm soát thông báo.
3. **Dài hạn:** trợ lý AI giải thích bài theo từng bước và phân tích chủ đề cần ôn từ dữ liệu tối thiểu cần thiết; đặt giới hạn chi phí/quota, bảo vệ dữ liệu trẻ em, theo dõi chất lượng. Khi lượng truy cập tăng, đo bottleneck trước khi scale; cân nhắc cache dữ liệu công khai, pool kết nối DB, queue cho tác vụ nền và nâng cấp dịch vụ theo nhu cầu.

Frontend dùng bearer token lưu trong local storage. Chỉ URL API và Firebase web configuration (các giá trị client công khai) được đưa vào frontend; không đặt password, database URL, Firebase service account hay secret trong biến `VITE_*`. Token đăng nhập trên domain Vercel tách biệt với domain Render; sau khi chuyển frontend, người dùng cần đăng nhập lại. Trước khi bật push trên Vercel, thêm domain Vercel vào Firebase project nếu Firebase yêu cầu domain web hợp lệ. Tài khoản service và VAPID private material tiếp tục chỉ ở backend Render; VAPID public key được API cung cấp cho browser.

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

StudySync không có chatbot AI. Chỉ tính năng tạo thời khóa biểu từ ảnh cần Gemini API key.

## Công khai thành link web

1. Tạo repository mới trên GitHub.
2. Đưa toàn bộ project lên GitHub, nhưng bỏ qua `.env`.
3. Truy cập [share.streamlit.io](https://share.streamlit.io), đăng nhập GitHub.
4. Chọn repository, branch và file chính `parent_app.py` nếu deploy bản Streamlit.
5. Bấm **Deploy**. Streamlit sẽ cấp một đường link công khai cho website.

## Tạo thời khóa biểu từ ảnh

Trong ô **Thời khóa biểu** có nút **Tạo từ ảnh**. Ảnh được gửi từ backend tới Gemini Flash để phân tích thành JSON thời khóa biểu. Bảng dựng ra là bản xem trước; chỉ khi bấm **Lưu vào thời khóa biểu** thì dữ liệu mới được ghi.

Tạo Gemini API key trong [Google AI Studio](https://aistudio.google.com/apikey), sau đó đặt biến `TIMETABLE_GEMINI_API_KEY` trong Render Environment hoặc `.env` local. Có thể đổi model bằng `TIMETABLE_GEMINI_MODEL` (mặc định `gemini-2.0-flash`). Không đưa key vào frontend, Git hoặc ảnh chụp log. Ảnh thời khóa biểu sẽ được gửi tới Google Gemini; hãy kiểm tra chính sách dữ liệu và quota của tài khoản API.

Nút tự ẩn nếu `TIMETABLE_GEMINI_API_KEY` chưa được cấu hình. Backend giới hạn ảnh 8 MB, yêu cầu model trả JSON theo schema, kiểm tra buổi/ngày/tiết rồi mới gửi bản xem trước.

**Ảnh nên chụp như thế nào:** chụp thẳng, đủ cả bảng, có đủ tiêu đề Thứ 2 đến Thứ 7, chữ rõ và không bị che. Ảnh chụp nghiêng hoặc tối thường đọc sai nhiều ô, nên luôn kiểm tra bảng xem trước.

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
- `PUBLIC_APP_URL` (URL HTTPS của frontend Vercel; domain này được dùng cho liên kết và icon push)
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
TIMETABLE_GEMINI_API_KEY     = <Gemini API key>
TIMETABLE_GEMINI_MODEL       = gemini-2.0-flash
```

Chỉ cần đặt Gemini key trên Web Service `dong-hanh`; không còn OCR service riêng. Nếu key bị thiếu hoặc quota/API key bị từ chối, chức năng tạo lịch từ ảnh sẽ báo lỗi nhưng các thao tác lịch thủ công vẫn hoạt động.

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
