# -*- coding: utf-8 -*-
"""
BACKEND SERVER CHO ỨNG DỤNG KIỂM TRA LẠI CAPTCHA (V2.6 - Quy trình tự động)
==================================================================================
"""

import os
import sys
import logging
import shutil
import subprocess
from collections import Counter
from flask import Flask, render_template, send_from_directory
from flask_socketio import SocketIO
import eventlet
import webbrowser
from threading import Timer

# Cấu hình để PyInstaller có thể tìm thấy các module cục bộ
try:
    base_path = sys._MEIPASS
except Exception:
    base_path = os.path.abspath(".")
sys.path.append(base_path)

try:
    from captcha_solver import solve_captcha
except ImportError:
    print("LỖI: Không thể import captcha_solver. Hãy đảm bảo tệp tồn tại.")
    sys.exit(1)

# --- CẤU HÌNH ---
log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)

app = Flask(__name__, template_folder='.', static_folder='static')
app.config['SECRET_KEY'] = 'secret!_for_captcha_rechecker_v2.6'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

CAPTCHA_FOLDER = "failed_captchas"
RESULT_FOLDER = "captcha_result"
TRAIN_SCRIPT = "train_captcha_model.py"
NUM_PREDICTIONS = 5
CONSENSUS_THRESHOLD = 4 
CAPTCHA_LENGTH = 5

def resource_path(relative_path):
    """ Lấy đường dẫn tuyệt đối đến tài nguyên, hoạt động cho cả môi trường dev và PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# --- ROUTES ---
@app.route('/')
def index():
    return render_template('rechecker_app.html')

@app.route('/images/<path:filename>')
def serve_image(filename):
    captcha_dir = resource_path(CAPTCHA_FOLDER)
    return send_from_directory(captcha_dir, filename)

@app.route('/results/<path:filename>')
def serve_result_image(filename):
    result_dir = resource_path(RESULT_FOLDER)
    return send_from_directory(result_dir, filename)

# --- SOCKETIO EVENTS ---
@socketio.on('connect')
def handle_connect():
    print("[Server] Client đã kết nối.")

@socketio.on('disconnect')
def handle_disconnect():
    print("[Server] Client đã ngắt kết nối.")

@socketio.on('get_images')
def handle_get_images():
    try:
        captcha_dir = resource_path(CAPTCHA_FOLDER)
        if not os.path.exists(captcha_dir): os.makedirs(captcha_dir)
            
        images = [f for f in os.listdir(captcha_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
        print(f"[Server] Tìm thấy {len(images)} ảnh trong '{CAPTCHA_FOLDER}'.")
        socketio.emit('image_list', {'images': images})

        if not images:
            socketio.start_background_task(shutdown_and_train, needs_training=False)

    except Exception as e:
        print(f"[Server Lỗi] Không thể đọc thư mục ảnh: {e}")
        socketio.emit('error', {'message': str(e)})

@socketio.on('solve_image')
def handle_solve_image(data):
    image_name = data.get('image_name')
    if not image_name:
        socketio.emit('error', {'message': 'Tên ảnh không hợp lệ.'}); return

    try:
        captcha_dir = resource_path(CAPTCHA_FOLDER)
        image_path = os.path.join(captcha_dir, image_name)
        
        if not os.path.exists(image_path):
            socketio.emit('error', {'message': f'Không tìm thấy ảnh: {image_name}'}); return

        print(f"[Server] Bắt đầu phân tích đa luồng cho: {image_name}")
        with open(image_path, "rb") as image_file:
            image_data_bytes = image_file.read()
        
        predictions = []
        for i in range(NUM_PREDICTIONS):
            prediction = solve_captcha(image_data_bytes)
            predictions.append(prediction)
            socketio.emit('prediction_result', {'attempt': i + 1, 'prediction': prediction})
            socketio.sleep(0.2)

        valid_predictions = [p for p in predictions if p and len(p) == CAPTCHA_LENGTH]
        
        consensus_achieved = False
        if valid_predictions:
            prediction_counts = Counter(valid_predictions)
            most_common = prediction_counts.most_common(1)[0]
            consensus_label, count = most_common

            if count >= CONSENSUS_THRESHOLD:
                consensus_achieved = True
                print(f"[Server] Đạt đồng thuận cho {image_name}: '{consensus_label}' (x{count})")
                new_filename = move_and_rename_file(image_name, consensus_label)
                socketio.emit('consensus_found', {'consensus_label': consensus_label, 'image_name': image_name, 'new_filename': new_filename})
            
        if not consensus_achieved:
            print(f"[Server] Không đạt đồng thuận cho {image_name}.")
            socketio.emit('consensus_failed', {'image_name': image_name})

        socketio.sleep(0.5)
        if not os.listdir(captcha_dir):
            socketio.start_background_task(shutdown_and_train)

    except Exception as e:
        print(f"[Server Lỗi] Lỗi trong quá trình giải mã: {e}")
        socketio.emit('error', {'message': str(e)})

def move_and_rename_file(original_name, new_label):
    try:
        src_folder = resource_path(CAPTCHA_FOLDER)
        dest_folder = resource_path(RESULT_FOLDER)
        if not os.path.exists(dest_folder): os.makedirs(dest_folder)

        original_path = os.path.join(src_folder, original_name)
        
        new_filename = f"{new_label}.png"
        dest_path = os.path.join(dest_folder, new_filename)
        counter = 1
        while os.path.exists(dest_path):
            new_filename = f"{new_label}_{counter}.png"
            dest_path = os.path.join(dest_folder, new_filename)
            counter += 1
            
        shutil.move(original_path, dest_path)
        print(f"[Server] Đã chuyển '{original_name}' thành '{new_filename}' trong '{RESULT_FOLDER}'.")
        return new_filename
    except Exception as e:
        print(f"[Server Lỗi] Không thể di chuyển file: {e}")
        return original_name

def run_training():
    print("\n" + "="*50)
    print("[Server] Bắt đầu quá trình tái huấn luyện mô hình...")
    print("="*50)
    socketio.emit('training_started', {})
    
    try:
        python_executable = sys.executable
        train_script_path = resource_path(TRAIN_SCRIPT)
        
        if not os.path.exists(train_script_path):
            print(f"[Server Lỗi] Không tìm thấy script huấn luyện: {TRAIN_SCRIPT}")
            socketio.emit('error', {'message': 'Không tìm thấy script huấn luyện.'})
            return

        creationflags = 0
        if sys.platform == "win32":
            creationflags = subprocess.CREATE_NO_WINDOW
        
        result = subprocess.run(
            [python_executable, train_script_path],
            capture_output=True, text=True, check=False, creationflags=creationflags
        )
        
        print(result.stdout)
        if result.returncode != 0:
            print("[Server Lỗi] Quá trình huấn luyện gặp lỗi.")
            print(result.stderr)
            socketio.emit('error', {'message': 'Quá trình huấn luyện gặp lỗi.'})
        else:
            print("[Server] Huấn luyện hoàn tất thành công!")
            socketio.emit('training_finished', {})

    except Exception as e:
        print(f"[Server Lỗi] Không thể chạy script huấn luyện: {e}")
        socketio.emit('error', {'message': f'Lỗi khi chạy script huấn luyện: {e}'})

def shutdown_and_train(needs_training=True):
    socketio.sleep(2)
    if needs_training:
        run_training()
        socketio.sleep(1)
    
    print("[Server] Công việc hoàn tất. Máy chủ sẽ tắt trong 3 giây.")
    socketio.emit('all_done')
    socketio.sleep(3)
    socketio.stop()

if __name__ == '__main__':
    print("="*60)
    print("Hệ Thống Phân Tích & Tái Huấn Luyện CAPTCHA - Backend Server v2.6")
    print("Đang khởi chạy máy chủ tại http://127.0.0.1:5001")
    print("="*60)
    
    Timer(1, lambda: webbrowser.open("http://127.0.0.1:5001")).start()
    
    eventlet.wsgi.server(eventlet.listen(('127.0.0.1', 5001)), app)
    
    print("[Server] Máy chủ đã tắt. Tiến trình kết thúc.")
