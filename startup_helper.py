# -*- coding: utf-8 -*-
"""
MODULE HỖ TRỢ TẠO SHORTCUT TRONG THƯ MỤC STARTUP (V2)
======================================================

Mô tả:
- (Cập nhật) Tạo shortcut trỏ đến chính tệp thực thi (.exe) với
  đối số `--headless`.
"""
import os
import sys
import subprocess

SHORTCUT_NAME = "AutoCustomsLookup.lnk"

def get_startup_folder():
    """Lấy đường dẫn đến thư mục Startup của người dùng hiện tại."""
    appdata = os.getenv('APPDATA')
    if not appdata:
        return None
    return os.path.join(appdata, 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')

def create_startup_shortcut():
    """
    Tạo một shortcut trong thư mục Startup bằng VBScript.
    """
    startup_path = get_startup_folder()
    if not startup_path:
        return False, "Không thể tìm thấy thư mục Startup."

    # Khi được đóng gói, sys.executable là đường dẫn đến tệp .exe
    # Khi chạy từ mã nguồn, nó là đường dẫn đến python.exe
    target_executable = sys.executable
    
    # Đối số để kích hoạt chế độ chạy nền
    arguments = "--headless"
    
    shortcut_path = os.path.join(startup_path, SHORTCUT_NAME)
    
    # Tạo một tệp VBScript tạm thời
    vbs_script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "create_shortcut.vbs")
    
    script_content = f'''
    Set oWS = WScript.CreateObject("WScript.Shell")
    sLinkFile = "{shortcut_path}"
    Set oLink = oWS.CreateShortcut(sLinkFile)
    oLink.TargetPath = "{target_executable}"
    oLink.Arguments = "{arguments}"
    oLink.Description = "Auto Customs Declaration Lookup"
    oLink.WorkingDirectory = "{os.path.dirname(os.path.abspath(__file__))}"
    oLink.Save
    '''
    
    try:
        with open(vbs_script_path, "w") as f:
            f.write(script_content)
        
        # Chạy script bằng wscript để không hiện cửa sổ console
        subprocess.run(["wscript", vbs_script_path], check=True, creationflags=subprocess.CREATE_NO_WINDOW)
        
        return True, "Đã bật tính năng tự động chạy khi mở máy."
    except Exception as e:
        return False, f"Lỗi khi tạo shortcut: {e}"
    finally:
        # Xóa tệp script tạm thời
        if os.path.exists(vbs_script_path):
            os.remove(vbs_script_path)

def delete_startup_shortcut():
    """Xóa shortcut khỏi thư mục Startup."""
    startup_path = get_startup_folder()
    if not startup_path:
        return False, "Không thể tìm thấy thư mục Startup."
        
    shortcut_path = os.path.join(startup_path, SHORTCUT_NAME)
    
    if os.path.exists(shortcut_path):
        try:
            os.remove(shortcut_path)
            return True, "Đã tắt tính năng tự động chạy khi mở máy."
        except Exception as e:
            return False, f"Lỗi khi xóa shortcut: {e}"
    else:
        return True, "Không tìm thấy shortcut để xóa."

def check_shortcut_exists():
    """Kiểm tra xem shortcut đã tồn tại hay chưa."""
    startup_path = get_startup_folder()
    if not startup_path:
        return False
        
    shortcut_path = os.path.join(startup_path, SHORTCUT_NAME)
    return os.path.exists(shortcut_path)
