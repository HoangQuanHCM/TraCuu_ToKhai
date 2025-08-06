# -*- coding: utf-8 -*-
"""
GIAO DIỆN ĐỒ HỌA ĐIỀU KHIỂN QUY TRÌNH TRA CỨU (V7.6 - Đã tách biệt)
======================================================================
"""

import tkinter as tk
from tkinter import scrolledtext, messagebox
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
import threading
import queue
import gspread
import pandas as pd
import sys
import json
import os
import time
from http.client import RemoteDisconnected

def resource_path(relative_path):
    """ Lấy đường dẫn tuyệt đối đến tài nguyên, hoạt động cho cả môi trường dev và PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

try:
    from batch_processor import run_batch_processing
    from startup_helper import create_startup_shortcut, delete_startup_shortcut, check_shortcut_exists
except ImportError as e:
    messagebox.showerror("Lỗi Import", f"Không tìm thấy tệp cần thiết: {e}. Vui lòng đảm bảo các tệp .py nằm cùng thư mục.")
    sys.exit(1)

RESULT_FIELDS = [
    "Tên luồng", "Ngày thông quan", "Ngày qua khu vực giám sát", "Mã hải quan",
    "Tên hải quan", "Mã loại hình", "Tên loại hình", "Năm đăng ký",
    "Ngày đăng ký", "Mã đơn vị"
]
CONFIG_FILE = "app_config.json"

class AppController:
    def __init__(self, root):
        self.root = root
        self.root.title("Công Cụ Tự Động Tra Cứu Tờ Khai v7.6")
        self.root.geometry("850x750")

        self.thread = None
        self.stop_event = threading.Event()
        self.q = queue.Queue()

        self.create_widgets()
        self.load_settings()
        self.periodic_call()

    def create_widgets(self):
        main_frame = ttk.Frame(self.root, padding="15")
        main_frame.pack(fill=tk.BOTH, expand=True)

        config_frame = ttk.LabelFrame(main_frame, text=" Cấu hình Google Sheets ", padding="15", bootstyle=PRIMARY)
        config_frame.pack(fill=tk.X, expand=False, pady=(0, 15))
        config_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(config_frame, text="URL Google Sheet:").grid(row=0, column=0, sticky="w", padx=5, pady=8)
        self.g_sheet_url = tk.StringVar()
        ttk.Entry(config_frame, textvariable=self.g_sheet_url, bootstyle=PRIMARY).grid(row=0, column=1, columnspan=3, sticky="ew", padx=5, pady=8)

        ttk.Label(config_frame, text="Tên Sheet:").grid(row=1, column=0, sticky="w", padx=5, pady=8)
        self.sheet_name = tk.StringVar(value="Sheet1")
        ttk.Entry(config_frame, textvariable=self.sheet_name, width=20).grid(row=1, column=1, sticky="w", padx=5, pady=8)

        ttk.Label(config_frame, text="Cột lấy Số TK:").grid(row=2, column=0, sticky="w", padx=5, pady=8)
        self.read_col = tk.StringVar(value="A")
        ttk.Entry(config_frame, textvariable=self.read_col, width=10).grid(row=2, column=1, sticky="w", padx=5, pady=8)

        ttk.Label(config_frame, text="Cột trả kết quả:").grid(row=2, column=2, sticky="w", padx=(20, 5), pady=8)
        self.write_col = tk.StringVar(value="F")
        ttk.Entry(config_frame, textvariable=self.write_col, width=10).grid(row=2, column=3, sticky="w", padx=5, pady=8)

        automation_frame = ttk.LabelFrame(main_frame, text=" Tùy chọn & Tự động hóa ", padding="15", bootstyle=PRIMARY)
        automation_frame.pack(fill=tk.X, expand=False, pady=(0, 15))
        automation_frame.grid_columnconfigure(0, weight=2)
        automation_frame.grid_columnconfigure(1, weight=1)

        ttk.Label(automation_frame, text="Chọn trường dữ liệu trả về:").grid(row=0, column=0, sticky="w", padx=5)
        self.result_field_var = tk.StringVar(value=RESULT_FIELDS[0])
        result_combobox = ttk.Combobox(automation_frame, textvariable=self.result_field_var, values=RESULT_FIELDS, state="readonly", bootstyle=PRIMARY)
        result_combobox.grid(row=1, column=0, sticky="ew", padx=5, pady=5)

        self.startup_var = tk.BooleanVar()
        startup_check = ttk.Checkbutton(automation_frame, text="Tự động chạy khi mở máy", variable=self.startup_var, bootstyle="success-round-toggle", command=self.toggle_startup_script)
        startup_check.grid(row=0, column=1, rowspan=2, sticky="w", padx=(20, 5))

        log_frame = ttk.LabelFrame(main_frame, text=" Điều khiển & Nhật ký hoạt động ", padding="10", bootstyle=INFO)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        button_frame = ttk.Frame(log_frame)
        button_frame.pack(fill=tk.X, pady=(5, 10))
        self.run_button = ttk.Button(button_frame, text="Bắt đầu", command=self.start_processing_thread, bootstyle=SUCCESS)
        self.run_button.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)
        self.stop_button = ttk.Button(button_frame, text="Dừng", command=self.stop_processing, state="disabled", bootstyle=DANGER)
        self.stop_button.pack(side=tk.LEFT, padx=5, expand=True, fill=tk.X)

        self.progress_bar = ttk.Progressbar(log_frame, orient="horizontal", mode="determinate", bootstyle=STRIPED)
        self.progress_bar.pack(fill=tk.X, expand=False, pady=(0, 10))
        self.log_area = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', height=15)
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def toggle_startup_script(self):
        self.save_settings()
        is_enabled = self.startup_var.get()
        if is_enabled:
            success, message = create_startup_shortcut()
        else:
            success, message = delete_startup_shortcut()
        
        if success:
            messagebox.showinfo("Thành công", message)
        else:
            messagebox.showerror("Lỗi", message)
            if is_enabled: self.startup_var.set(False)

    def log(self, message, style=""):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message + "\n", style)
        self.log_area.config(state='disabled')
        self.log_area.see(tk.END)
        self.log_area.tag_config("SUCCESS", foreground="green")
        self.log_area.tag_config("ERROR", foreground="red")
        self.log_area.tag_config("INFO", foreground="blue")

    def periodic_call(self):
        self.root.after(200, self.periodic_call)
        try:
            msg = self.q.get(block=False)
            status, message, value = msg.get('status'), msg.get('message'), msg.get('value')
            
            if status == 'PROGRESS':
                self.log(f"[Tiến trình] {message}", "INFO")
                if value is not None: self.progress_bar['value'] = value
            elif status in ['ERROR', 'FINAL_ERROR', 'FATAL_ERROR']:
                self.log(f"[LỖI] {message}", "ERROR")
            elif status == 'RESULT':
                so_tk, data = msg.get('so_tk'), msg.get('data')
                self.log(f"[THÀNH CÔNG] Tờ khai {so_tk} - Luồng: {data.get('Tên luồng', 'N/A')}", "SUCCESS")
                self.write_single_result_to_sheet(so_tk, data)
            elif status == 'STOPPED' or status == 'DONE':
                self.log(f"[HOÀN TẤT] {message}", "INFO")
                self.progress_bar['value'] = 100
                self.run_button.config(state="normal")
                self.stop_button.config(state="disabled")
                self.thread = None
        except queue.Empty:
            pass

    def start_processing_thread(self):
        if not all([self.g_sheet_url.get(), self.sheet_name.get(), self.read_col.get(), self.write_col.get()]):
            messagebox.showerror("Thiếu thông tin", "Vui lòng điền đầy đủ thông tin cấu hình.")
            return
        
        self.save_settings()
        self.run_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.log_area.config(state='normal'); self.log_area.delete('1.0', tk.END); self.log_area.config(state='disabled')
        self.progress_bar['value'] = 0
        self.stop_event.clear()

        self.thread = threading.Thread(target=self.worker, daemon=True)
        self.thread.start()

    def stop_processing(self):
        if self.thread and self.thread.is_alive():
            self.log("[YÊU CẦU DỪNG] Chương trình sẽ dừng sau khi hoàn tất tác vụ hiện tại...", "INFO")
            self.stop_event.set()
            self.stop_button.config(state="disabled")

    def worker(self):
        try:
            url, sheet_name = self.g_sheet_url.get(), self.sheet_name.get()
            read_col, write_col = self.read_col.get().upper(), self.write_col.get().upper()
            
            self.q.put({'status': 'PROGRESS', 'message': 'Đang kết nối đến Google Sheets...'})
            
            credentials_path = resource_path('credentials.json')
            
            if not os.path.exists(credentials_path):
                raise FileNotFoundError("Không tìm thấy tệp credentials.json. Vui lòng đảm bảo tệp này nằm cùng thư mục với ứng dụng.")

            gc = gspread.service_account(filename=credentials_path)
            
            spreadsheet = gc.open_by_url(url)
            self.worksheet = spreadsheet.worksheet(sheet_name)
            
            all_records = self.worksheet.get_all_records()
            df = pd.DataFrame(all_records)
            read_col_name = df.columns[gspread.utils.a1_to_rowcol(read_col + '1')[1] - 1]
            write_col_name = df.columns[gspread.utils.a1_to_rowcol(write_col + '1')[1] - 1]
            df_todo = df[df[write_col_name] == '']
            tasks = [{'so_tk': str(row[read_col_name]).strip(), 'row_index': index + 2} for index, row in df_todo.iterrows() if str(row[read_col_name]).strip().isdigit()]

            if not tasks: raise ValueError('Không có tờ khai nào cần xử lý.')
            
            self.tasks_map = {task['so_tk']: task['row_index'] for task in tasks}
            so_tk_list_to_process = list(self.tasks_map.keys())

            self.q.put({'status': 'PROGRESS', 'message': f'Tìm thấy {len(so_tk_list_to_process)} tờ khai cần xử lý.'})

            for result in run_batch_processing(so_tk_list_to_process, self.stop_event):
                self.q.put(result)
                if self.stop_event.is_set(): break

        except FileNotFoundError as e:
            self.q.put({'status': 'FATAL_ERROR', 'message': f"Lỗi: {e}. Hãy đảm bảo tệp credentials.json tồn tại và đã chia sẻ Sheet với client_email."})
        except gspread.exceptions.SpreadsheetNotFound:
             self.q.put({'status': 'FATAL_ERROR', 'message': "Lỗi: Không tìm thấy Google Sheet. Vui lòng kiểm tra lại URL."})
        except gspread.exceptions.WorksheetNotFound:
            self.q.put({'status': 'FATAL_ERROR', 'message': f"Lỗi: Không tìm thấy Sheet có tên '{sheet_name}'. Vui lòng kiểm tra lại Tên Sheet."})
        except Exception as e:
            self.q.put({'status': 'FATAL_ERROR', 'message': f"Lỗi nghiêm trọng: {e}"})
        
        if self.stop_event.is_set():
            self.q.put({'status': 'STOPPED', 'message': 'Chương trình đã dừng theo yêu cầu của người dùng.'})
        else:
            self.q.put({'status': 'DONE', 'message': 'Đã hoàn tất tất cả các tác vụ.'})

    def write_single_result_to_sheet(self, so_tk, data):
        MAX_WRITE_RETRIES = 3
        RETRY_DELAY_SECONDS = 5
        for attempt in range(MAX_WRITE_RETRIES):
            try:
                row_to_update = self.tasks_map.get(so_tk)
                if not row_to_update: return

                write_col_index = gspread.utils.a1_to_rowcol(self.write_col.get().upper() + '1')[1]
                selected_field = self.result_field_var.get()
                result_value = data.get(selected_field, "N/A")
                result_str_to_write = f"'{result_value}"
                
                self.worksheet.update_cell(row_to_update, write_col_index, result_str_to_write)
                return 
            
            except (gspread.exceptions.APIError, RemoteDisconnected) as e:
                self.q.put({'status': 'ERROR', 'message': f'Lỗi mạng khi ghi kết quả cho TK {so_tk} (lần thử {attempt + 1}/{MAX_WRITE_RETRIES})...'})
                if attempt < MAX_WRITE_RETRIES - 1:
                    time.sleep(RETRY_DELAY_SECONDS)
                else:
                    self.q.put({'status': 'FINAL_ERROR', 'message': f'Không thể ghi kết quả cho TK {so_tk} sau {MAX_WRITE_RETRIES} lần thử.'})
            except Exception as e:
                self.q.put({'status': 'FATAL_ERROR', 'message': f'Lỗi không xác định khi ghi kết quả cho TK {so_tk}: {e}'})
                return

    def save_settings(self):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}

        if 'gui_app' not in config:
            config['gui_app'] = {}
        
        config['gui_app'] = {
            'g_sheet_url': self.g_sheet_url.get(),
            'sheet_name': self.sheet_name.get(),
            'read_col': self.read_col.get(),
            'write_col': self.write_col.get(),
            'result_field': self.result_field_var.get()
        }

        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=4)

    def load_settings(self):
        try:
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
            
            gui_settings = config.get('gui_app', {})
            self.g_sheet_url.set(gui_settings.get('g_sheet_url', ''))
            self.sheet_name.set(gui_settings.get('sheet_name', 'Sheet1'))
            self.read_col.set(gui_settings.get('read_col', 'A'))
            self.write_col.set(gui_settings.get('write_col', 'F'))
            
            saved_field = gui_settings.get('result_field', RESULT_FIELDS[0])
            if saved_field in RESULT_FIELDS:
                self.result_field_var.set(saved_field)

        except (FileNotFoundError, json.JSONDecodeError):
            pass
        
        self.startup_var.set(check_shortcut_exists())

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == '--headless':
        from headless_logic import run_headless_mode
        run_headless_mode()
    else:
        root = ttk.Window(themename="litera")
        app = AppController(root)
        root.mainloop()
