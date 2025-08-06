# -*- coding: utf-8 -*-
"""
HUẤN LUYỆN MÔ HÌNH NHẬN DẠNG KÝ TỰ CAPTCHA (V3 - Không dùng scikit-learn)
===========================================================================
"""

import os
import cv2
import numpy as np
import pickle
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, TensorDataset
from sklearn.model_selection import train_test_split
import imutils
from captcha_solver import SimpleLabelEncoder, CaptchaNet

# --- CÁC THAM SỐ CẤU HÌNH ---
CAPTCHA_IMAGE_FOLDER = "captcha_result"
MODEL_FILENAME = "captcha_model.pth"
MODEL_LABELS_FILENAME = "label_encoder.pkl"
IMAGE_WIDTH = 20
IMAGE_HEIGHT = 20
CAPTCHA_LENGTH = 5


# --- CÁC HÀM VÀ LỚP KHÁC ---
def preprocess_and_segment(image_path):
    image = cv2.imread(image_path)
    if image is None: return []
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lower_blue = np.array([90, 80, 2])
    upper_blue = np.array([150, 255, 255])
    mask = cv2.inRange(hsv, lower_blue, upper_blue)
    opening = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    closing = cv2.morphologyEx(opening, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    contours = cv2.findContours(closing.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = imutils.grab_contours(contours)
    char_contours = [c for c in contours if cv2.contourArea(c) > 15 and cv2.boundingRect(c)[3] > 10]
    if len(char_contours) < CAPTCHA_LENGTH: return []
    char_contours = sorted(char_contours, key=cv2.contourArea, reverse=True)[:CAPTCHA_LENGTH]
    char_contours = sorted(char_contours, key=lambda c: cv2.boundingRect(c)[0])
    if len(char_contours) != CAPTCHA_LENGTH: return []
    segmented_chars = [cv2.resize(closing[y:y+h, x:x+w], (IMAGE_WIDTH, IMAGE_HEIGHT)) for x,y,w,h in [cv2.boundingRect(c) for c in char_contours]]
    return segmented_chars


def main():
    print("[INFO] Loading and preparing data...")
    data, labels = [], []
    
    for filename in os.listdir(CAPTCHA_IMAGE_FOLDER):
        if not filename.lower().endswith((".png", ".jpg", ".jpeg")): continue
        image_path = os.path.join(CAPTCHA_IMAGE_FOLDER, filename)
        captcha_text = os.path.splitext(filename)[0].split('_')[0]
        if len(captcha_text) != CAPTCHA_LENGTH: continue
        segmented_chars = preprocess_and_segment(image_path)
        if len(segmented_chars) == CAPTCHA_LENGTH:
            for char_text, char_image in zip(captcha_text, segmented_chars):
                data.append(char_image)
                labels.append(char_text)

    if not data:
        print("[ERROR] No data was loaded.")
        return

    print(f"[INFO] Found {len(data)} individual characters.")
    data = np.array(data, dtype="float32") / 255.0
    data = np.expand_dims(data, axis=1)

    le = SimpleLabelEncoder()
    labels_encoded = le.fit_transform(labels)

    (X_train, X_test, y_train, y_test) = train_test_split(
        data, labels_encoded, test_size=0.2, random_state=42, stratify=labels_encoded)

    train_loader = DataLoader(TensorDataset(torch.from_numpy(X_train), torch.from_numpy(y_train).type(torch.LongTensor)), batch_size=32, shuffle=True)

    print("[INFO] Building and training the model...")
    model = CaptchaNet(num_classes=len(le.classes_))
    criterion = nn.CrossEntropyLoss()
    optimizer = optim.Adam(model.parameters(), lr=0.001)

    epochs = 30
    for epoch in range(epochs):
        model.train()
        running_loss = 0.0
        for inputs, targets in train_loader:
            optimizer.zero_grad(); outputs = model(inputs); loss = criterion(outputs, targets)
            loss.backward(); optimizer.step(); running_loss += loss.item()
        print(f"Epoch {epoch+1}/{epochs}, Loss: {running_loss/len(train_loader):.4f}")

    print("[INFO] Evaluating and saving the model...")
    model.eval()
    with torch.no_grad():
        outputs = model(torch.from_numpy(X_test))
        _, predicted = torch.max(outputs.data, 1)
        accuracy = 100 * (predicted == torch.from_numpy(y_test)).sum().item() / len(y_test)
        print(f"[INFO] Test accuracy: {accuracy:.2f}%")

    torch.save(model.state_dict(), MODEL_FILENAME)
    print(f"[INFO] Model saved to {MODEL_FILENAME}")
    with open(MODEL_LABELS_FILENAME, "wb") as f:
        pickle.dump(le, f)
    print(f"[INFO] Label encoder saved to {MODEL_LABELS_FILENAME}")
    
    print("\n[SUCCESS] Training process completed!")

if __name__ == "__main__":
    main()
