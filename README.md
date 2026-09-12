# Robot-nhặt-rác

Đây là project mô hình robot thu rác tự động
File Python được dùng để kết nối bluetooth HC-06 trên arduino với laptop để điều khiển và kiểm tra robot
Để kết nối thành công cần thực hiện các bước như sau:
1. Tìm bluetooth HC-06 trên laptop, sẽ có 2 thiết bị chọn thiết bị yêu cầu mật khẩu, điền mật khẩu 1234
2. Vào device manager tìm COM có trong driver ví dụ COM4, COM5
3. Mở Python code và chỉnh đúng COM của HC-06 trên config
4. Khởi động code, cài python -m pip install pyserial nếu báo lỗi
5. Connect ở 9600 baud rate.
<img width="564" height="499" alt="Screenshot 2026-09-12 165542" src="https://github.com/user-attachments/assets/995e99b8-930c-4d3f-837f-f12b0c0abbdd" />
Ảnh app điều khiển bluetooth trên laptop
