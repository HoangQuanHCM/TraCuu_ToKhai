# -*- coding: utf-8 -*-
"""
MODULE XỬ LÝ LOGIC TRA CỨU HÀNG LOẠT (V3.3 - Cải tiến logic chờ đợi)
===================================================================
"""
import time
import base64
import os
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException, NoSuchElementException

# Import solver từ file cục bộ
from captcha_solver import solve_captcha

URL = "https://www.customs.gov.vn/index.jsp?pageId=136&cid=93"
FAILED_CAPTCHA_FOLDER = "failed_captchas"
MAX_RETRIES_PER_TK = 5  # Tăng số lần thử lại CAPTCHA
MA_DOANH_NGHIEP = "3700482964"
SO_CMT = "079172041842"

def run_batch_processing(so_tk_list, stop_event):
    """
    Hàm xử lý tra cứu hàng loạt với logic chờ đợi và xử lý lỗi được cải tiến.
    """
    os.makedirs(FAILED_CAPTCHA_FOLDER, exist_ok=True)
    options = Options()
    # options.add_argument("--headless") # Bỏ comment để chạy ẩn
    options.add_argument("--disable-gpu")
    options.add_argument("--log-level=3")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    driver = None
    total_tk = len(so_tk_list)
    try:
        yield {'status': 'PROGRESS', 'message': 'Đang khởi tạo trình duyệt...', 'value': 0}
        driver = webdriver.Chrome(options=options)
        # Tăng thời gian chờ chính lên 15 giây
        wait = WebDriverWait(driver, 15)
        yield {'status': 'PROGRESS', 'message': f'Đang tải trang: {URL}...', 'value': 0}
        driver.get(URL)
        
        for index, so_tk in enumerate(so_tk_list):
            if stop_event.is_set():
                yield {'status': 'STOPPED', 'message': 'Người dùng đã yêu cầu dừng.'}
                return

            progress_value = int(((index) / total_tk) * 100)
            yield {'status': 'PROGRESS', 'message': f'Bắt đầu xử lý tờ khai {index + 1}/{total_tk}: {so_tk}', 'value': progress_value}

            try:
                # 1. Điền thông tin vào form
                so_tk_input = wait.until(EC.presence_of_element_located((By.ID, "soTK")))
                so_tk_input.clear()
                driver.find_element(By.ID, "maDN").clear()
                driver.find_element(By.ID, "soCMT").clear()
                
                so_tk_input.send_keys(so_tk)
                driver.find_element(By.ID, "maDN").send_keys(MA_DOANH_NGHIEP)
                driver.find_element(By.ID, "soCMT").send_keys(SO_CMT)

                for attempt in range(MAX_RETRIES_PER_TK):
                    if stop_event.is_set():
                        yield {'status': 'STOPPED', 'message': 'Người dùng đã yêu cầu dừng.'}
                        return
                        
                    yield {'status': 'PROGRESS', 'message': f'Tờ khai {so_tk}: Lần thử CAPTCHA {attempt + 1}/{MAX_RETRIES_PER_TK}...', 'value': progress_value}
                    time.sleep(1) # Chờ một chút để captcha mới có thể tải về
                    
                    # 2. Giải CAPTCHA
                    captcha_element = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, "#mainCaptcha img")))
                    img_src = captcha_element.get_attribute('src')
                    base64_string = img_src.split('data:image/jpg;base64,')[1]
                    img_data = base64.b64decode(base64_string)
                    predicted_label = solve_captcha(img_data)
                    
                    if not predicted_label:
                        yield {'status': 'ERROR', 'message': f'Tờ khai {so_tk}: Lần {attempt + 1} không giải được CAPTCHA. Lấy CAPTCHA mới.'}
                        driver.find_element(By.CSS_SELECTOR, 'button[onclick="getCaptcha()"]').click()
                        continue

                    # 3. Điền CAPTCHA và nhấn nút
                    captcha_input_element = driver.find_element(By.ID, "check-input")
                    # Sử dụng Javascript để điền giá trị, ổn định hơn send_keys
                    driver.execute_script(f"arguments[0].value = '{predicted_label}';", captcha_input_element)
                    
                    # Lấy tham chiếu đến bảng kết quả *cũ* (nếu có) trước khi nhấn
                    try:
                        old_result_table = driver.find_element(By.CLASS_NAME, "tbl-TTTK")
                    except NoSuchElementException:
                        old_result_table = None

                    driver.find_element(By.ID, "btn-search").click()
                    
                    # 4. PHƯƠNG THỨC CHỜ ĐỢI THÔNG MINH
                    try:
                        # Chờ đợi một cách linh hoạt:
                        # - Hoặc là bảng kết quả mới xuất hiện (thành công)
                        # - Hoặc là thông báo lỗi CAPTCHA sai xuất hiện
                        # - Hoặc là bảng kết quả cũ biến mất (dấu hiệu đang tải)
                        # Tăng thời gian chờ ở đây lên 10 giây
                        long_wait = WebDriverWait(driver, 10)
                        
                        # Điều kiện phức hợp: chờ cho đến khi có kết quả hoặc có thông báo lỗi
                        long_wait.until(
                            EC.any_of(
                                EC.presence_of_element_located((By.CLASS_NAME, "tbl-TTTK")),
                                EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Sai mã kiểm tra')]"))
                            )
                        )

                        # Sau khi chờ, kiểm tra xem kết quả là gì
                        try:
                            # Trường hợp thành công: tìm thấy bảng kết quả
                            result_table = driver.find_element(By.CLASS_NAME, "tbl-TTTK")
                            
                            # Kỹ thuật kiểm tra "Stale Element": đảm bảo đây là bảng MỚI
                            if old_result_table and old_result_table.id == result_table.id:
                                yield {'status': 'ERROR', 'message': f'Tờ khai {so_tk}: Lần {attempt + 1} - trang không cập nhật kết quả mới.'}
                                # Tải lại captcha và thử lại
                                driver.find_element(By.CSS_SELECTOR, 'button[onclick="getCaptcha()"]').click()
                                continue

                            rows = result_table.find_elements(By.TAG_NAME, "tr")
                            result_data = {cells[0].text.strip(): cells[1].text.strip() for row in rows if len(cells := row.find_elements(By.TAG_NAME, "td")) == 2}
                            
                            if not result_data:
                                 yield {'status': 'ERROR', 'message': f'Tờ khai {so_tk}: Tìm thấy bảng kết quả nhưng không có dữ liệu.'}
                                 break # Thoát khỏi vòng lặp attempt, xử lý tờ khai tiếp theo
                            
                            yield {'status': 'RESULT', 'so_tk': so_tk, 'data': result_data}
                            break # Thoát khỏi vòng lặp attempt vì đã thành công
                            
                        except NoSuchElementException:
                            # Trường hợp CAPTCHA sai: không tìm thấy bảng, nhưng có thể có thông báo lỗi
                            message = f'Tờ khai {so_tk}: Lần thử {attempt + 1} thất bại (CAPTCHA sai).'
                            yield {'status': 'ERROR', 'message': message}
                            filepath = os.path.join(FAILED_CAPTCHA_FOLDER, f"failed_{so_tk}_{predicted_label}_{int(time.time())}.png")
                            with open(filepath, 'wb') as f: f.write(img_data)
                            # Trang web không tự refresh captcha, ta phải tự nhấn
                            driver.find_element(By.CSS_SELECTOR, 'button[onclick="getCaptcha()"]').click()
                            
                    except TimeoutException:
                        # Hết 10 giây mà không thấy bảng kết quả hay thông báo lỗi
                        message = f'Tờ khai {so_tk}: Lần thử {attempt + 1} - trang không phản hồi sau khi nhấn nút.'
                        yield {'status': 'ERROR', 'message': message}
                        # Lưu lại captcha để kiểm tra
                        filepath = os.path.join(FAILED_CAPTCHA_FOLDER, f"failed_timeout_{so_tk}_{predicted_label}_{int(time.time())}.png")
                        with open(filepath, 'wb') as f: f.write(img_data)
                    
                    # Nếu là lần thử cuối cùng mà vẫn thất bại
                    if attempt == MAX_RETRIES_PER_TK - 1:
                        yield {'status': 'FINAL_ERROR', 'message': f'Không thể lấy thông tin cho tờ khai {so_tk} sau {MAX_RETRIES_PER_TK} lần thử.'}

            except Exception as e:
                yield {'status': 'ERROR', 'message': f'Lỗi hệ thống khi xử lý tờ khai {so_tk}: {e}'}
                try:
                    driver.get(URL) # Tải lại trang để bắt đầu lại
                    time.sleep(2)
                except WebDriverException:
                    yield {'status': 'FATAL_ERROR', 'message': 'Mất kết nối với trình duyệt. Vui lòng khởi động lại.'}
                    return
                continue # Bỏ qua tờ khai hiện tại và tiếp tục với tờ khai tiếp theo
                
    except WebDriverException as e:
        yield {'status': 'FATAL_ERROR', 'message': f'Lỗi nghiêm trọng với Selenium/WebDriver: {e}. Hãy đảm bảo chromedriver tương thích với phiên bản Chrome của bạn.'}
    except Exception as e:
        yield {'status': 'FATAL_ERROR', 'message': f'Lỗi không xác định trong quá trình xử lý: {e}'}
    finally:
        if driver: 
            driver.quit()
        if not stop_event.is_set():
            yield {'status': 'DONE', 'message': 'Hoàn tất quá trình tra cứu.', 'value': 100}