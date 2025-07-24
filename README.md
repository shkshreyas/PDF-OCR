# PDF OCR Service 🔍📄

A modern, scalable PDF OCR service that converts scanned PDFs into fully searchable and selectable documents with **perfect invisible text overlays**. Built with FastAPI, Docker, and professional OCR engines.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.9+-brightgreen.svg)
![Docker](https://img.shields.io/badge/docker-supported-blue.svg)
![Platform](https://img.shields.io/badge/platform-linux%20%7C%20windows%20%7C%20macos-lightgrey.svg)

## ✨ Features

* **🔍 Perfect Text Selection** - Native text selection, copying, and searching
* **👻 Invisible Text Overlays** - OCR text is completely invisible but fully selectable
* **🎨 Modern Animated UI** - Beautiful, responsive interface with smooth animations
* **⚡ High Performance** - Multiple OCR strategies
* **🌐 Multi-language Support** - English, French, German, Spanish, and more
* **📱 Responsive Design** - Works perfectly on desktop and mobile devices
* **🐳 Docker Ready** - Easy deployment with Docker and Docker Compose
* **🔒 Production Ready** - Secure, scalable, and enterprise-grade

## 🚀 Quick Start

### Option 1: Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/shkshreyas/PDF-OCR.git
cd PDF-OCR

# Run with Docker Compose
docker-compose up --build

# Access the service
open http://localhost:8000
```

### Option 2: Local Installation

```bash
# Clone the repository
git clone https://github.com/shkshreyas/PDF-OCR.git
cd PDF-OCR

# Install system dependencies (Ubuntu/Debian)
sudo apt update
sudo apt install -y tesseract-ocr tesseract-ocr-eng ghostscript

# Install Python dependencies
pip install -r requirements.txt

# Run the application
python app.py
```

## 📋 Requirements

### System Dependencies

* **Python 3.9+**
* **Tesseract OCR** - Open source OCR engine
* **Ghostscript** - PDF processing
* **Docker** (optional, for containerized deployment)

### Python Dependencies

```text
fastapi==0.104.1
uvicorn[standard]==0.24.0
python-multipart==0.0.6
PyMuPDF==1.23.8
pytesseract==0.3.10
ocrmypdf==15.4.4
Pillow==10.1.0
```

## 💻 Usage

### Web Interface

1. **Open your browser** to `http://localhost:8000`
2. **Upload a PDF** by dragging and dropping or clicking to browse
3. **Click "Convert to Searchable PDF"**
4. **Download** your processed PDF with invisible, selectable text

### API Usage

#### Upload and Process PDF

```bash
curl -X POST "http://localhost:8000/upload-pdf/" \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@your-document.pdf"
```

**Response:**

```json
{
  "message": "PDF processed successfully with perfect text selection",
  "file_id": "abc123",
  "download_url": "/download/abc123",
  "has_selectable_text": true,
  "character_count": 1250
}
```

#### Download Processed PDF

```bash
curl -X GET "http://localhost:8000/download/abc123" \
     -H "accept: application/pdf" \
     --output searchable-document.pdf
```


## 🏗️ Project Structure

````text
pdf-ocr-service/
├── app.py                 # Main FastAPI application
├── requirements.txt       # Python dependencies
├── Dockerfile             # Docker configuration
├── docker-compose.yml     # Docker Compose setup
├── static/
│   └── index.html         # Modern web interface
├── README.md              # This file
├── LICENSE                # MIT License

````
## 🔧 Configuration

### Environment Variables

| Variable             | Default  | Description                   |
|----------------------|----------|-------------------------------|
| `PORT`               | `8000`   | Server port                   |
| `FILE_CLEANUP_HOURS` | `1`      | Hours before file cleanup     |
| `MAX_FILE_SIZE`      | `20971520` | Maximum file size (20MB)    |

### Docker Configuration

```yaml
# docker-compose.yml
services:
  pdf-ocr-app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - PORT=8000
    volumes:
      - pdf_uploads:/tmp/pdf_uploads
      - pdf_outputs:/tmp/pdf_outputs
````
## 📝 License & Contact

This project is licensed under the [MIT License](LICENSE).\
For questions, issues, or contributions, please contact: [shkshreyaskumar@gmail.com](mailto\:shkshreyaskumar@gmail.com)
