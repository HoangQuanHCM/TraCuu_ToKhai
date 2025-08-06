# -*- coding: utf-8 -*-
"""
CÔNG CỤ THU THẬP VÀ GÁN NHÃN CAPTCHA THỦ CÔNG
=============================================

Mô tả:
- Sử dụng Selenium để truy cập website và lấy ảnh CAPTCHA.
- Hiển thị ảnh CAPTCHA cho người dùng bằng OpenCV.
- Nhận dữ liệu nhập từ bàn phím của người dùng (gán nhãn).
- Lưu ảnh CAPTCHA gốc với tên file là nhãn do người dùng nhập.
- Lặp lại quá trình để thu thập một bộ dữ liệu lớn.

Cách chạy:
1. Chạy file Python này.
2. Một cửa sổ trình duyệt Chrome sẽ mở ra và truy cập trang web.
3. Một cửa sổ có tên "Nhap Captcha" sẽ hiện lên, hiển thị ảnh CAPTCHA.
4. Nhìn vào ảnh và nhập các ký tự bạn thấy vào trong cửa sổ dòng lệnh (terminal).
5. Nhấn Enter. Ảnh sẽ được lưu và quá trình sẽ lặp lại với ảnh mới.
"""

import os
import base64
import cv2
import numpy as np
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException

def collect_manual_captchas(num_captchas=100):
    """
    Hàm chính để lấy CAPTCHA liên tục, hiển thị cho người dùng nhập liệu,
    và lưu lại để tạo bộ dữ liệu cho mô hình CNN.

    Args:
        num_captchas (int): Số lượng ảnh CAPTCHA muốn thu thập.
    """
    # 1. Cấu hình
    url = "https://www.customs.gov.vn/index.jsp?pageId=136&cid=93"
    output_folder = "captcha_result"
    os.makedirs(output_folder, exist_ok=True)
    print(f"Các ảnh CAPTCHA sẽ được lưu vào thư mục: '{output_folder}'")

    # 2. Khởi tạo Selenium
    options = Options()
    # Không dùng headless mode để người dùng có thể thấy trình duyệt
    # options.add_argument("--headless") 
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1280,720")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    options.add_argument('--log-level=3')
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    driver = None
    try:
        print("Đang khởi tạo trình duyệt Selenium...")
        driver = webdriver.Chrome(options=options)
        print(f"Đang kết nối đến: {url}")
        driver.get(url)
        wait = WebDriverWait(driver, 20)

        # 3. Vòng lặp thu thập dữ liệu
        collected_count = 0
        while collected_count < num_captchas:
            print("-" * 50)
            print(f"Đang lấy ảnh CAPTCHA thứ {collected_count + 1}/{num_captchas}...")

            try:
                # Chờ cho ảnh CAPTCHA xuất hiện và lấy dữ liệu
                captcha_element = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#mainCaptcha img"))
                )
                
                # Đợi một chút để đảm bảo ảnh đã được tải hoàn toàn
                time.sleep(0.5)

                img_src = captcha_element.get_attribute('src')
                if not img_src or not img_src.startswith('data:image/jpg;base64,'):
                    print("Lỗi: Không lấy được dữ liệu ảnh base64. Đang thử tải lại trang...")
                    driver.refresh()
                    continue

                base64_string = img_src.split('data:image/jpg;base64,')[1]
                img_data = base64.b64decode(base64_string)

                # Decode ảnh để hiển thị và lưu
                nparr = np.frombuffer(img_data, np.uint8)
                img_original = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                # Kiểm tra xem ảnh có hợp lệ không
                if img_original is None:
                    print("Không thể decode ảnh. Bỏ qua và tải lại.")
                    driver.refresh()
                    continue

                # Hiển thị ảnh CAPTCHA
                cv2.imshow("Nhap Captcha", img_original)
                cv2.waitKey(1)  # Cần thiết để cửa sổ được vẽ lên màn hình

                # Nhận input từ người dùng trong console
                prompt = f"[{collected_count + 1}/{num_captchas}] Nhập ký tự (gõ 'quit' để thoát, Enter để bỏ qua): "
                user_input = input(prompt).strip().lower()

                cv2.destroyAllWindows()

                # Xử lý input của người dùng
                if user_input == 'quit':
                    print("Đã nhận lệnh thoát. Dừng chương trình.")
                    break
                
                if user_input:
                    # Tạo tên file dựa trên input của người dùng
                    base_filename = f"{user_input}.png"
                    filepath = os.path.join(output_folder, base_filename)
                    
                    # Xử lý trường hợp file đã tồn tại để tránh ghi đè
                    counter = 1
                    while os.path.exists(filepath):
                        filename = f"{user_input}_{counter}.png"
                        filepath = os.path.join(output_folder, filename)
                        counter += 1
                    
                    # Lưu ảnh
                    cv2.imwrite(filepath, img_original)
                    print(f"Đã lưu ảnh vào: {filepath}")
                    collected_count += 1
                else:
                    print("Bỏ qua ảnh này.")

                # Tải lại trang để lấy CAPTCHA mới
                if collected_count < num_captchas:
                    print("Đang tải CAPTCHA mới...")
                    driver.refresh()

            except TimeoutException:
                print("Lỗi: Hết thời gian chờ CAPTCHA xuất hiện. Đang thử tải lại trang...")
                driver.refresh()
            except Exception as e:
                print(f"Đã xảy ra lỗi trong vòng lặp: {e}")
                print("Thử tải lại trang...")
                try:
                    driver.refresh()
                except WebDriverException as refresh_error:
                    print(f"Không thể tải lại trang: {refresh_error}. Dừng chương trình.")
                    break
    
    except WebDriverException as e:
        print(f"Lỗi nghiêm trọng với WebDriver: {e}")
        print("Hãy đảm bảo ChromeDriver đã được cài đặt và phiên bản tương thích với trình duyệt Chrome của bạn.")
    finally:
        if driver:
            print("Đóng trình duyệt.")
            driver.quit()
        cv2.destroyAllWindows()

if __name__ == "__main__":
    # Bắt đầu quá trình thu thập 100 ảnh
    collect_manual_captchas(num_captchas=100)
    print("\nHoàn tất quá trình thu thập dữ liệu!")
