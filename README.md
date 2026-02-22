 # Image Resizer & Compressor Pro
<img width="1258" height="902" alt="Capture" src="https://github.com/user-attachments/assets/2a382011-5ddf-4ccb-a75a-de357a9e16ad" />
<img width="1227" height="882" alt="1112" src="https://github.com/user-attachments/assets/b356c0f9-beb4-4300-bf7d-551158ebf1e5" />
 

A professional web-based Image Resizer and Compressor built with FastAPI and Pillow.

This application allows users to resize, compress, and convert images while maintaining aspect ratio and image quality. It supports bulk processing and ZIP downloads, making it ideal for content creators, e-commerce platforms, and developers.

## 🚀 Features

- Supports JPG, JPEG, PNG, WEBP, BMP, TIFF, GIF (static)
- Custom width & height resizing
- Presets: 1024x1024, 800x800, 1920x1080
- Percentage resize (50%, 25%)
- Aspect ratio protection (no stretch)
- Compression control (10%–100%)
- Format conversion (JPG, PNG, WEBP)
- Bulk image processing
- Download all images as ZIP
- Clean, modern white + green professional UI

## 🛠 Tech Stack

Backend:
- FastAPI
- Pillow
- Python

Frontend:
- HTML
- CSS
- JavaScript

## 📦 Use Cases

- E-commerce product image optimization
- Website performance optimization
- Bulk social media image resizing
- Developer image processing workflows

 
## Run
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open: http://127.0.0.1:8000
