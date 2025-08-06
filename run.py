# -*- coding: utf-8 -*-
"""
TỆP KHỞI CHẠY CHÍNH (V2)
=========================
Kịch bản này điều phối toàn bộ quy trình:
1. Kiểm tra thư mục 'failed_captchas'.
2. Nếu có file, chạy máy chủ phân tích và đợi hoàn tất.
3. Nếu không có file, bỏ qua giai đoạn 1.
4. Khởi chạy ứng dụng tra cứu chính (GUI).
"""

import subprocess
import sys
import os

CAPTCHA_FOLDER = "failed_captchas"

def resource_path(relative_path):
    """ Lấy đường dẫn tuyệt đối đến tài nguyên, hoạt động cho cả môi trường dev và PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def check_if_captchas_exist():
    """Kiểm tra xem có file CAPTCHA nào cần xử lý không."""
    captcha_dir = resource_path(CAPTCHA_FOLDER)
    if not os.path.isdir(captcha_dir):
        return False
    # Kiểm tra xem có bất kỳ file ảnh nào trong thư mục không
    for filename in os.listdir(captcha_dir):
        if filename.lower().endswith(('.png', '.jpg', '.jpeg')):
            return True
    return False

try:
    python_executable = sys.executable
    recheck_server_script = resource_path('recheck_server.py')
    gui_app_script = resource_path('gui_app.py')

    # --- Giai đoạn 1: Kiểm tra và chạy máy chủ phân tích CAPTCHA (nếu cần) ---
    if check_if_captchas_exist():
        print("--- GIAI ĐOẠN 1: KIỂM TRA VÀ HUẤN LUYỆN LẠI CAPTCHA ---")
        print("Phát hiện có file CAPTCHA cần xử lý. Đang khởi chạy máy chủ...")
        
        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW
            
        recheck_process = subprocess.run([python_executable, recheck_server_script], creationflags=creationflags)
        
        if recheck_process.returncode != 0:
            print("\n--- LỖI: Quá trình kiểm tra CAPTCHA đã kết thúc với lỗi. Dừng chương trình. ---")
            sys.exit(1) # Thoát nếu giai đoạn 1 thất bại
    else:
        print("--- GIAI ĐOẠN 1: BỎ QUA ---")
        print("Không tìm thấy file CAPTCHA nào trong thư mục 'failed_captchas'.")

    # --- Giai đoạn 2: Khởi chạy ứng dụng tra cứu chính ---
    print("\n--- GIAI ĐOẠN 2: KHỞI CHẠY ỨNG DỤNG TRA CỨU CHÍNH ---")
    subprocess.run([python_executable, gui_app_script])

except FileNotFoundError:
    print(f"LỖI: Không tìm thấy tệp kịch bản. Vui lòng đảm bảo 'recheck_server.py' và 'gui_app.py' nằm cùng thư mục.")
except Exception as e:
    print(f"Đã xảy ra lỗi không mong muốn: {e}")
