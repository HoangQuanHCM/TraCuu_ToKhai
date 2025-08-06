# -*- coding: utf-8 -*-
"""
KỊCH BẢN CHẠY NỀN (HEADLESS) - Sửa lỗi xác thực Service Account
==============================================================
"""

import os
import sys
import json
import logging
import threading
import gspread
import pandas as pd

def resource_path(relative_path):
    """ Lấy đường dẫn tuyệt đối đến tài nguyên, hoạt động cho cả môi trường dev và PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(os.path.dirname(__file__))
    return os.path.join(base_path, relative_path)

# Thêm thư mục hiện tại vào sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

try:
    from batch_processor import run_batch_processing
except ImportError:
    # Cấu hình logging cơ bản để ghi lại lỗi import
    log_dir = os.path.dirname(os.path.abspath(__file__))
    logging.basicConfig(filename=os.path.join(log_dir, 'scheduler_error.log'), level=logging.ERROR)
    logging.error("Không thể import 'batch_processor'. Đảm bảo các tệp nằm cùng thư mục.")
    sys.exit(1)

# --- CẤU HÌNH ---
CONFIG_FILE = "app_config.json"
LOG_FILE = "scheduler.log"

def setup_logging():
    """Cấu hình logging để ghi vào tệp."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        filename=os.path.join(current_dir, LOG_FILE),
        filemode='a'
    )

def run_headless_mode():
    """Hàm chính để thực hiện quy trình chạy nền."""
    setup_logging()
    logging.info("="*20 + " BẮT ĐẦU PHIÊN LÀM VIỆC TỰ ĐỘNG (STARTUP) " + "="*20)

    try:
        # 1. Tải cấu hình
        logging.info("Đang tải cấu hình từ 'app_config.json'...")
        config_path = resource_path(CONFIG_FILE)
        with open(config_path, 'r') as f:
            config = json.load(f)
        gui_settings = config.get('gui_app', {})
        
        url = gui_settings.get('g_sheet_url')
        sheet_name = gui_settings.get('sheet_name')
        read_col = gui_settings.get('read_col', 'A').upper()
        write_col = gui_settings.get('write_col', 'F').upper()
        selected_field = gui_settings.get('result_field')

        if not all([url, sheet_name, read_col, write_col, selected_field]):
            raise ValueError("Cấu hình trong 'app_config.json' bị thiếu.")
        
        # 2. Kết nối Google Sheet và lấy công việc
        logging.info("Đang kết nối đến Google Sheets...")
        
        # === SỬA LỖI XÁC THỰC ===
        # Sử dụng gspread.service_account cho đúng loại credentials
        credentials_path = resource_path('credentials.json')

        if not os.path.exists(credentials_path):
            raise FileNotFoundError("Không tìm thấy tệp credentials.json. Vui lòng đảm bảo tệp này nằm cùng thư mục với ứng dụng.")
            
        gc = gspread.service_account(filename=credentials_path)
        # === KẾT THÚC SỬA LỖI ===
        
        spreadsheet = gc.open_by_url(url)
        worksheet = spreadsheet.worksheet(sheet_name)
        
        logging.info("Đang đọc và lọc dữ liệu từ Sheet...")
        all_records = worksheet.get_all_records()
        df = pd.DataFrame(all_records)

        read_col_name = df.columns[gspread.utils.a1_to_rowcol(read_col + '1')[1] - 1]
        write_col_name = df.columns[gspread.utils.a1_to_rowcol(write_col + '1')[1] - 1]

        df_todo = df[df[write_col_name] == '']
        tasks = [{'so_tk': str(row[read_col_name]).strip(), 'row_index': index + 2} for index, row in df_todo.iterrows() if str(row[read_col_name]).strip().isdigit()]

        if not tasks:
            logging.info("Không có tờ khai nào cần xử lý. Kết thúc phiên.")
            return

        tasks_map = {task['so_tk']: task['row_index'] for task in tasks}
        so_tk_list_to_process = list(tasks_map.keys())
        logging.info(f"Tìm thấy {len(so_tk_list_to_process)} tờ khai cần xử lý.")

        # 3. Chạy quy trình tra cứu
        stop_event = threading.Event() 
        for result in run_batch_processing(so_tk_list_to_process, stop_event):
            status = result.get('status')
            message = result.get('message')
            
            if status == 'PROGRESS':
                logging.info(f"[Tiến trình] {message}")
            elif status in ['ERROR', 'FINAL_ERROR', 'FATAL_ERROR']:
                logging.error(f"[LỖI] {message}")
            elif status == 'RESULT':
                so_tk = result.get('so_tk')
                data = result.get('data')
                logging.info(f"[THÀNH CÔNG] Tờ khai {so_tk} - Luồng: {data.get('Tên luồng', 'N/A')}")
                
                try:
                    row_to_update = tasks_map.get(so_tk)
                    if row_to_update:
                        write_col_index = gspread.utils.a1_to_rowcol(write_col + '1')[1]
                        result_value = data.get(selected_field, "N/A")
                        result_str_to_write = f"'{result_value}"
                        worksheet.update_cell(row_to_update, write_col_index, result_str_to_write)
                        logging.info(f"Đã ghi kết quả cho tờ khai {so_tk} vào Sheet.")
                except Exception as e:
                    logging.error(f"Lỗi khi ghi kết quả cho TK {so_tk}: {e}")

    except Exception as e:
        logging.error(f"LỖI NGHIÊM TRỌNG TRONG QUÁ TRÌNH CHẠY NỀN: {e}", exc_info=True)
    finally:
        logging.info("="*20 + " KẾT THÚC PHIÊN LÀM VIỆC TỰ ĐỘNG " + "="*20 + "\n")
