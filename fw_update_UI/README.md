# FW Update Tool — Vite + MUI

Giao diện React thay thế UI HTML/JavaScript trong `../frontend/`. Dùng các thư viện MUI, Emotion và `@mui/icons-material` đã cài; không dùng CSS hoặc CDN Bootstrap từ UI cũ.

## Các màn hình

- **Main Menu:** Mass Update, Manual Command Send và About.
- **Manual Command Send:** quét/kết nối/ngắt COM, gửi HEX, 8 quick commands, kết quả có Copy và terminal.
- **Mass Update:** bắt buộc chọn M12/M18 (không chọn sẵn), chọn `.bin`/`.csv`, nhập phiên bản firmware, Start/Stop, tiến độ, tỷ lệ PASS/FAIL, status gọn, Space để Start và Focus Mode có mật khẩu trong phiên làm việc. Không có card guideline.

**Mass Update chạy Auto PCBA**: Start flash và xác minh board đầu tiên ngay, không dò tháo/gắn trước. Sau board đầu tiên mới lặp chu kỳ chờ tháo → chờ gắn lại → tự update. Mỗi lần nhấn Start mới đều update ngay board đang gắn. Chỉ tính PASS/FAIL khi nhận `onMassResult`; Stop trước kết quả không tính thêm board. Đổi file, tool type hoặc phiên bản sẽ xóa xác minh cũ, giữ thống kê của phiên. Khi Auto PCBA đang chờ hoặc flash, khóa cấu hình và Main Menu; Stop kết thúc cả chu kỳ và mở lại điều khiển.

Auto PCBA gửi đúng hai lệnh kiểm tra: Target theo M12/M18 và Check FW Version (`01 00 03 00 0D 04 00 15`). Chỉ xét byte đầu phản hồi, không phân tích hoặc so sánh giá trị version khi dò gắn/tháo. Sau mỗi lần update, chạy đúng thứ tự:

1. **Waiting for removal:** cả hai `80/81` nghĩa là còn gắn; ít nhất một `82/83` xác nhận đã tháo.
2. **Waiting for next PCBA:** có `82/83` nghĩa là chưa gắn; chỉ khi cả hai `80/81` mới xác nhận đã gắn lại.
3. **Update:** tự flash và xác minh firmware, rồi quay về bước 1. Không có bước xác nhận còn gắn sau update.

Hai phản hồi phải thuộc cùng một lượt kiểm tra; không ghép kết quả giữa các lượt. Xác nhận còn gắn hoặc gắn lại yêu cầu cả hai là `80/81`. Xác nhận đã tháo chỉ cần Target hoặc FW version là `82/83`, kể cả khi lệnh kia trả `80/81`, timeout hoặc `85`. Nếu không có `82/83`, timeout và `85` không xác nhận đã tháo. Mất serial kết thúc chu kỳ và yêu cầu kết nối lại. Các gói kiểm tra không tính thêm board. Poll mỗi 0,5 giây, timeout 500 ms cho từng lệnh; vẫn áp dụng flow control và sequence matching của command runner. Firmware dùng snapshot đã kiểm tra lúc Start cho toàn bộ batch.

Trong mock, Mass Update có hai nút **Insert PCBA / Remove PCBA** để mô phỏng gắn/tháo; chúng không xuất hiện trong desktop production.

Mass Update vừa chiều cao cửa sổ: header và footer luôn hiển thị; phần điều khiển cuộn riêng, Terminal giãn theo vùng còn lại và cuộn log bên trong. Trên màn hình hẹp, điều khiển và log chia chiều cao thay vì kéo dài trang. Focus Mode ẩn điều khiển/log, giữ Start/Stop trong màn hình và để status card giãn theo khoảng trống còn lại. Các bước chờ gắn/tháo/gắn lại gửi lại cả hai lệnh sau phản hồi chưa đúng hoặc timeout, kể cả khi phản hồi trước là `85`. Không giới hạn số lượt thử; chỉ chuyển bước khi đạt điều kiện của bước đó, Stop để kết thúc. Mất kết nối COM vẫn báo lỗi và dừng.

Status card gọn ở chế độ thường và co giãn trong Focus Mode. Khi **Updating firmware. Keep the PCBA connected.**, animation mô phỏng dữ liệu chạy trên mạch vào chip, lõi chip sáng theo nhịp. Animation nằm trong vùng cố định, không tạo thanh cuộn trong status card. Khi thành công, hiển thị **Update complete. Remove the PCBA.** cùng subtitle **Actual FW** (phiên bản thực tế đọc được) và **FW setting** (phiên bản đã đặt cho lần update đó). Chuyển sang chờ board mới thì hiển thị **Insert the next PCBA to continue.** và bỏ thông tin FW của board cũ. Nếu update lỗi, hiển thị **Update failed. Remove the PCBA.**; chi tiết lỗi nằm trong log. Stop hoặc lỗi kết nối vẫn có trạng thái riêng. Animation dừng khi kết thúc update và tôn trọng cài đặt giảm chuyển động. Việc đối chiếu phiên bản sau flash vẫn thuộc bước xác minh firmware, tách khỏi vòng dò gắn/tháo.

Các trạng thái khác cũng có animation riêng: **chờ** có mũi tên gắn board và ba chấm chạy tuần tự; **thành công** vẽ dấu tick xanh kèm nhịp sáng nhẹ; **thất bại** vẽ dấu X đỏ, rung ngắn rồi giữ cảnh báo. Mọi hiệu ứng đều nằm trong khung cố định, không tạo scrollbar và tắt khi bật giảm chuyển động. Trạng thái Stop giữ biểu tượng tĩnh.

## Môi trường đã kiểm tra

Windows, Node.js **22.13.1**, npm **10.9.2**, Python **3.13.11**. Các phiên bản dependency chính xác nằm trong `package-lock.json`.

Các lệnh bên dưới chạy từ thư mục gốc repository. Dùng `npm.cmd` trên PowerShell để tránh phụ thuộc execution policy của `npm.ps1`.

```powershell
npm.cmd --prefix fw_update_UI ci
python -m pip install -r backend/requirements.txt
```

Desktop dùng pywebview với Microsoft Edge WebView2 Runtime và driver COM của thiết bị.

## Xem thử trên trình duyệt

```powershell
npm.cmd --prefix fw_update_UI run dev
```

Vite dev mặc định dùng **mock**: COM mô phỏng, phản hồi mẫu, không gửi dữ liệu đến phần cứng. Màn hình thao tác luôn hiện nhãn SIMULATION. Có thể kéo thả firmware hoặc Browse bằng file picker của trình duyệt.

## Chạy desktop với Python thật

```powershell
npm.cmd --prefix fw_update_UI run build
python backend/main.py
```

Hoặc double-click `run.bat`: kiểm tra dependency, build UI với `VITE_API_MODE=bridge`, sau đó mở desktop. Launcher ưu tiên Python trong `.venv`, rồi `venv`, rồi Python hệ thống hoặc `py -3`. `run.ps1` gọi cùng launcher này. Dùng `run.bat --check` để chỉ kiểm tra/build, không mở cửa sổ.

Production mặc định dùng **bridge**. `backend/app_paths.py` trỏ đến `fw_update_UI/dist/index.html`. pywebview phục vụ bundle qua HTTP nội bộ để tải ES modules; Vite đặt `base: './'` để asset hoạt động khi đóng gói. Nếu chưa build, backend báo lệnh cần chạy. Nếu thiếu Python bridge, UI báo lỗi sau 8 giây và không tự chuyển sang mô phỏng.

Trong desktop, Browse mở native dialog và trả về ID firmware do backend đăng ký. UI gửi ID này khi Start, không gửi đường dẫn tùy ý. Backend kiểm tra lại kích thước và thời gian sửa file trước khi tạo snapshot trong bộ nhớ. Kéo thả chỉ dùng trong mock.

## Phát triển với hot reload và bridge thật

Terminal 1:

```powershell
$env:VITE_API_MODE = 'bridge'
npm.cmd --prefix fw_update_UI run dev -- --host 127.0.0.1 --port 5173
```

Terminal 2:

```powershell
$env:FW_UPDATE_UI_URL = 'http://127.0.0.1:5173'
python backend/main.py
```

Xóa các biến môi trường khi không còn dùng. `VITE_API_MODE` chỉ nhận `mock` hoặc `bridge` và được chốt lúc Vite khởi động/build. Không đặt secrets trong biến `VITE_*`. Khi cần build để xem thử bằng `vite preview`, có thể đặt `VITE_API_MODE=mock`; không phát hành bundle đó cho desktop.

## Kiểm tra

```powershell
npm.cmd --prefix fw_update_UI run lint
npm.cmd --prefix fw_update_UI test
npm.cmd --prefix fw_update_UI run build
```

Unit tests ở `tests/frontend/` dùng Node test runner: Python bridge readiness, lỗi/cancellation, callback cleanup, điều kiện Start, thống kê, kết quả cũ và mô phỏng Start/Stop. Test chạy trong cùng process để dùng được trong môi trường Windows hạn chế tạo subprocess.

Kiểm thử UI tự động dùng Chrome DevTools Protocol, không cần cài thêm thư viện. Mở Edge/Chrome headless với `--remote-debugging-port=9222` và một `--user-data-dir` riêng, chạy Vite dev ở `http://127.0.0.1:5173`, rồi:

```powershell
node tests/frontend/mass-scroll-smoke.mjs
```

Có thể đổi URL bằng `UI_TEST_URL` và `CDP_URL`. Screenshot được lưu trong `fw_update_UI/logs/ui-smoke/` (không commit). Browser smoke chỉ xác minh mock; native dialog, giao tiếp serial và flash firmware thật cần kiểm tra với phần cứng.

Kiểm tra bundle production và Python bridge thật trong cửa sổ WebView2 ẩn:

```powershell
python tests/backend/desktop_smoke.py
```

Bài kiểm tra này tải asset, chuyển trang, quét COM và nhận callback log; không mở kết nối serial hoặc flash thiết bị. Cần cho phép chạy WebView2 trên máy, ngoài sandbox hạn chế khởi tạo trình duyệt.

Backend ghi log ra terminal và `logs/app.log`, xoay vòng 5 MiB × 3 backup. Bản executable dùng `%LOCALAPPDATA%/FWUpdateTool/logs/app.log`; có thể đặt `FW_UPDATE_LOG_DIR` để đổi nơi ghi. UI giữ tối đa 2.000 dòng trong bộ nhớ. Firmware được xử lý từ snapshot trong RAM, không tạo hoặc xóa thư mục temp dùng chung.

## Cấu trúc

```text
src/api/          Adapter duy nhất cho Python và mock
src/components/   COM, terminal, file picker, thống kê và dialogs dùng chung
src/hooks/        Phiên kết nối/log/busy và workflow firmware dùng chung
src/pages/        Home, Manual, Mass Update
src/state/        Reducer và validation của Mass Update
src/theme.js      Theme MUI, màu đỏ và typography
```

Các trang thao tác được lazy load. Điều hướng dùng React state để không reload pywebview hoặc cần cấu hình router trên server tĩnh. Mật khẩu Focus Mode chỉ giữ trong RAM; đây là khóa thao tác UI trong phiên, không phải cơ chế xác thực người dùng.

## Đóng gói

Build production trước rồi đưa toàn bộ `fw_update_UI/dist/` vào bundle tại đúng đường dẫn `fw_update_UI/dist/`, ví dụ thêm tham số sau vào cấu hình PyInstaller hiện có trên Windows:

```text
--add-data "fw_update_UI/dist;fw_update_UI/dist"
```

Không cần đưa source `frontend/` cũ hoặc `node_modules/` vào executable. Backend tự resolve bundle từ `sys._MEIPASS` khi chạy bản frozen.
