# -*- coding: utf-8 -*-
"""
MODULE GIẢI MÃ CAPTCHA (V2.3 - Tương thích .exe)
==================================================
"""
import cv2
import pickle
import numpy as np
import imutils
import torch
import torch.nn as nn
import os
import sys

def resource_path(relative_path):
    """ Lấy đường dẫn tuyệt đối đến tài nguyên, hoạt động cho cả môi trường dev và PyInstaller """
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- CÁC THAM SỐ CẤU HÌNH CỐ ĐỊNH ---
MODEL_FILENAME = "captcha_model.pth"
MODEL_LABELS_FILENAME = "label_encoder.pkl"
IMAGE_WIDTH = 20
IMAGE_HEIGHT = 20
CAPTCHA_LENGTH = 5

# --- LỚP TÙY CHỈNH (phải có ở đây để pickle hoạt động) ---
class SimpleLabelEncoder:
    def __init__(self):
        self.classes_ = []
        self._map = {}
        self._inverse_map = {}
    def fit(self, labels): self.classes_ = np.unique(labels); self._map = {label: i for i, label in enumerate(self.classes_)}; self._inverse_map = {i: label for i, label in enumerate(self.classes_)}; return self
    def fit_transform(self, labels): self.fit(labels); return self.transform(labels)
    def transform(self, labels): return np.array([self._map.get(label, -1) for label in labels])
    def inverse_transform(self, encoded_labels): return np.array([self._inverse_map.get(i, '?') for i in encoded_labels])

class CaptchaNet(nn.Module):
    def __init__(self, num_classes):
        super(CaptchaNet, self).__init__()
        self.conv1 = nn.Conv2d(1, 32, kernel_size=5, padding='same'); self.relu1 = nn.ReLU(); self.pool1 = nn.MaxPool2d(kernel_size=2)
        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding='same'); self.relu2 = nn.ReLU(); self.pool2 = nn.MaxPool2d(kernel_size=2)
        self.flatten = nn.Flatten(); self.fc1 = nn.Linear(64 * 5 * 5, 512); self.relu3 = nn.ReLU(); self.dropout = nn.Dropout(0.5)
        self.fc2 = nn.Linear(512, num_classes)
    def forward(self, x):
        x = self.pool1(self.relu1(self.conv1(x))); x = self.pool2(self.relu2(self.conv2(x))); x = self.flatten(x)
        x = self.relu3(self.fc1(x)); x = self.dropout(x); x = self.fc2(x); return x

# --- NẠP MODEL MỘT LẦN KHI MODULE ĐƯỢC IMPORT ---
model, le = None, None
try:
    labels_path = resource_path(MODEL_LABELS_FILENAME)
    model_path = resource_path(MODEL_FILENAME)
    if os.path.exists(labels_path) and os.path.getsize(labels_path) > 0:
        with open(labels_path, "rb") as f:
            le = pickle.load(f)
    if le and os.path.exists(model_path):
        model = CaptchaNet(num_classes=len(le.classes_))
        model.load_state_dict(torch.load(model_path, map_location=torch.device('cpu')))
        model.eval()
except Exception as e:
    with open("error_log.txt", "a") as f: f.write(f"Error loading model: {e}\n")

def _preprocess_and_segment(image):
    if image is None: return []
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lower_blue, upper_blue = np.array([90, 80, 2]), np.array([150, 255, 255])
    mask = cv2.inRange(hsv, lower_blue, upper_blue)
    opening = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours = cv2.findContours(closing.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(imutils.grab_contours(contours), key=cv2.contourArea, reverse=True)
    char_contours = [c for c in contours if cv2.contourArea(c) > 15 and cv2.boundingRect(c)[3] > 10]
    if len(char_contours) < CAPTCHA_LENGTH: return []
    char_contours = sorted(char_contours, key=cv2.contourArea, reverse=True)[:CAPTCHA_LENGTH]
    char_contours = sorted(char_contours, key=lambda c: cv2.boundingRect(c)[0])
    if len(char_contours) != CAPTCHA_LENGTH: return []
    return [cv2.resize(closing[y:y+h, x:x+w], (IMAGE_WIDTH, IMAGE_HEIGHT)) for x,y,w,h in [cv2.boundingRect(c) for c in char_contours]]

def solve_captcha(image_data_bytes):
    if model is None or le is None: return None
    nparr = np.frombuffer(image_data_bytes, np.uint8)
    img_original = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    segmented_chars = _preprocess_and_segment(img_original)
    if len(segmented_chars) != CAPTCHA_LENGTH: return None
    X_pred = np.array(segmented_chars, dtype="float32") / 255.0
    X_pred = torch.from_numpy(np.expand_dims(X_pred, axis=1))
    with torch.no_grad():
        outputs = model(X_pred)
        _, predictions = torch.max(outputs, 1)
        predicted_label = "".join(le.inverse_transform(predictions.numpy()))
    return predicted_label