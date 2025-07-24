from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
import subprocess
import os
import tempfile
import uuid
from pathlib import Path
import logging
import asyncio
from typing import Optional
import shutil
import fitz  # PyMuPDF for verification and fallback
import pytesseract
from PIL import Image
import io

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PDF OCR Service", 
    version="2.0.0",
    description="Convert PDFs to searchable PDFs with perfect text selection using OCRmyPDF"
)

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Create directories for storing files
UPLOAD_DIR = Path(tempfile.gettempdir()) / "pdf_uploads"
OUTPUT_DIR = Path(tempfile.gettempdir()) / "pdf_outputs"
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

# File cleanup after 1 hour to manage storage
FILE_CLEANUP_HOURS = 1

def cleanup_old_files():
    """Clean up files older than FILE_CLEANUP_HOURS"""
    import time
    current_time = time.time()
    cutoff_time = current_time - (FILE_CLEANUP_HOURS * 3600)
    
    for directory in [UPLOAD_DIR, OUTPUT_DIR]:
        if directory.exists():
            for file_path in directory.iterdir():
                if file_path.is_file() and file_path.stat().st_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        logger.info(f"Cleaned up old file: {file_path.name}")
                    except Exception as e:
                        logger.error(f"Error cleaning up {file_path}: {e}")

def check_dependencies():
    """Check if required OCR dependencies are available"""
    dependencies = {
        'ocrmypdf': 'ocrmypdf --version',
        'tesseract': 'tesseract --version',
        'ghostscript': 'gs --version'
    }
    
    missing = []
    for name, cmd in dependencies.items():
        try:
            result = subprocess.run(cmd.split(), capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                logger.info(f"✓ {name} is available")
            else:
                missing.append(name)
        except (subprocess.SubprocessError, FileNotFoundError, subprocess.TimeoutExpired):
            missing.append(name)
    
    return missing

def create_searchable_pdf_with_ocrmypdf(input_pdf_path: str, output_pdf_path: str) -> tuple[bool, str]:
    """Create a searchable PDF using OCRmyPDF with fallback strategies"""
    try:
        cleanup_old_files()
        
        strategies = [
            {
                'name': 'Basic OCR',
                'cmd': [
                    'ocrmypdf',
                    '--language', 'eng',
                    '--force-ocr',
                    input_pdf_path,
                    output_pdf_path
                ]
            },
            {
                'name': 'OCR with optimization',
                'cmd': [
                    'ocrmypdf',
                    '--language', 'eng',
                    '--force-ocr',
                    '--optimize', '1',
                    '--rotate-pages',
                    input_pdf_path,
                    output_pdf_path
                ]
            },
            {
                'name': 'OCR with background removal',
                'cmd': [
                    'ocrmypdf',
                    '--language', 'eng',
                    '--force-ocr',
                    '--remove-background',
                    '--optimize', '1',
                    input_pdf_path,
                    output_pdf_path
                ]
            }
        ]
        
        for i, strategy in enumerate(strategies):
            try:
                logger.info(f"Trying strategy {i+1}: {strategy['name']}")
                
                if os.path.exists(output_pdf_path):
                    os.remove(output_pdf_path)
                
                result = subprocess.run(
                    strategy['cmd'],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=tempfile.gettempdir()
                )
                
                if result.returncode == 0:
                    logger.info(f"✅ {strategy['name']} completed successfully")
                    return True, f"Success using {strategy['name']}"
                else:
                    error_msg = result.stderr.strip() if result.stderr else "Unknown error"
                    logger.warning(f"❌ {strategy['name']} failed: {error_msg}")
                    
                    if i == len(strategies) - 1:
                        return False, f"All OCR strategies failed. Last error: {error_msg}"
                    
                    continue
                    
            except subprocess.TimeoutExpired:
                logger.warning(f"⏰ {strategy['name']} timed out")
                continue
            except Exception as e:
                logger.warning(f"💥 {strategy['name']} crashed: {str(e)}")
                continue
        
        return False, "All OCR strategies failed"
            
    except Exception as e:
        error_msg = f"Error running OCRmyPDF: {str(e)}"
        logger.error(error_msg)
        return False, error_msg
def create_invisible_text_layer(input_pdf_path: str, output_pdf_path: str) -> tuple[bool, str]:
    """Create invisible text layer using PDF content streams"""
    import fitz
    
    doc = None
    try:
        doc = fitz.open(input_pdf_path)
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            existing_text = page.get_text().strip()
            
            if not existing_text or len(existing_text) < 50:
                # Get OCR data
                mat = fitz.Matrix(3.0, 3.0)
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                image = Image.open(io.BytesIO(img_data)).convert('RGB')
                
                ocr_data = pytesseract.image_to_data(
                    image, 
                    lang='eng', 
                    config='--oem 3 --psm 6',
                    output_type=pytesseract.Output.DICT
                )
                
                # Build invisible text content stream
                img_w, img_h = image.size
                pdf_rect = page.rect
                x_scale = pdf_rect.width / (img_w / 3.0)
                y_scale = pdf_rect.height / (img_h / 3.0)
                
                # Create content stream for invisible text
                content_stream = []
                content_stream.append("BT")  # Begin text
                content_stream.append("3 Tr")  # Set rendering mode to invisible (3)
                content_stream.append("/Helv 12 Tf")  # Set font
                
                n_boxes = len(ocr_data['level'])
                for i in range(n_boxes):
                    text = ocr_data['text'][i].strip()
                    confidence = int(ocr_data['conf'][i]) if ocr_data['conf'][i] != '-1' else 0
                    
                    if text and confidence > 40:
                        (x, y, w, h) = (
                            ocr_data['left'][i], 
                            ocr_data['top'][i], 
                            ocr_data['width'][i], 
                            ocr_data['height'][i]
                        )
                        
                        # Calculate PDF coordinates
                        pdf_x = x * x_scale
                        pdf_y = pdf_rect.height - (y * y_scale)  # Flip Y coordinate
                        font_size = max(min(h * y_scale * 0.85, 72), 4)
                        
                        # Add text positioning and content
                        content_stream.append(f"{font_size} TL")  # Set leading
                        content_stream.append(f"{pdf_x} {pdf_y} Td")  # Move to position
                        content_stream.append(f"({text}) Tj")  # Show text
                
                content_stream.append("ET")  # End text
                
                # Insert the invisible text stream
                text_content = "\n".join(content_stream)
                
                try:
                    # Insert the content stream into the page
                    page.wrap_contents()
                    new_content = page.read_contents().decode('utf-8', errors='ignore')
                    new_content += "\n" + text_content
                    page.set_contents(new_content.encode('utf-8'))
                    
                except Exception as stream_error:
                    logger.warning(f"Content stream insertion failed: {stream_error}")
                    continue
        
        doc.save(output_pdf_path, garbage=4, deflate=True, clean=True)
        return True, "Success using invisible text layer"
        
    except Exception as e:
        logger.error(f"Text layer method failed: {str(e)}")
        return False, f"Text layer method failed: {str(e)}"
    finally:
        if doc:
            doc.close()

def create_searchable_pdf_fallback(input_pdf_path: str, output_pdf_path: str) -> tuple[bool, str]:
    """Fallback method using PyMuPDF with completely invisible text overlays"""
    doc = None
    try:
        logger.info("Using PyMuPDF fallback method with invisible overlays...")
        doc = fitz.open(input_pdf_path)
        total_pages = len(doc)
        
        for page_num in range(total_pages):
            try:
                page = doc[page_num]
                existing_text = page.get_text().strip()
                
                if not existing_text or len(existing_text) < 50:
                    # Extract text using OCR with higher DPI
                    mat = fitz.Matrix(3.0, 3.0)  # Higher resolution for better accuracy
                    pix = page.get_pixmap(matrix=mat)
                    img_data = pix.tobytes("png")
                    image = Image.open(io.BytesIO(img_data)).convert('RGB')
                    
                    # Get OCR data with improved settings
                    ocr_data = pytesseract.image_to_data(
                        image, 
                        lang='eng', 
                        config='--oem 3 --psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789.,!?:;-()[]{}"\' ',
                        output_type=pytesseract.Output.DICT
                    )
                    
                    # Calculate precise scaling factors
                    img_w, img_h = image.size
                    pdf_rect = page.rect
                    x_scale = pdf_rect.width / (img_w / 3.0)  # Account for 3x matrix scaling
                    y_scale = pdf_rect.height / (img_h / 3.0)
                    
                    # Create invisible text overlays
                    n_boxes = len(ocr_data['level'])
                    for i in range(n_boxes):
                        text = ocr_data['text'][i].strip()
                        confidence = int(ocr_data['conf'][i]) if ocr_data['conf'][i] != '-1' else 0
                        
                        if text and confidence > 40:  # Higher confidence threshold
                            (x, y, w, h) = (
                                ocr_data['left'][i], 
                                ocr_data['top'][i], 
                                ocr_data['width'][i], 
                                ocr_data['height'][i]
                            )
                            
                            # Scale coordinates to PDF space
                            rect = fitz.Rect(
                                x * x_scale,
                                y * y_scale,
                                (x + w) * x_scale,
                                (y + h) * y_scale
                            )
                            
                            # Calculate font size to match original exactly
                            original_height = h * y_scale
                            font_size = original_height * 0.85
                            font_size = max(min(font_size, 72), 4)
                            
                            try:
                                # Method 1: Create invisible text widget (BEST APPROACH)
                                text_widget = fitz.Widget()
                                text_widget.field_type = fitz.PDF_WIDGET_TYPE_TEXT
                                text_widget.rect = rect
                                text_widget.field_value = text
                                text_widget.text_fontsize = font_size
                                text_widget.fill_color = None  # No background
                                text_widget.border_color = None  # No border
                                text_widget.text_color = (1, 1, 1, 0)  # Completely transparent text
                                
                                # Add the invisible widget to the page
                                page.add_widget(text_widget)
                                
                            except Exception as widget_error:
                                try:
                                    # Method 2: Use text annotation with invisible appearance
                                    text_annot = page.add_text_annot(
                                        fitz.Point(rect.x0, rect.y0), 
                                        text
                                    )
                                    text_annot.set_info(content=text)
                                    text_annot.set_rect(rect)
                                    text_annot.set_colors({"stroke": (1, 1, 1, 0), "fill": (1, 1, 1, 0)})
                                    text_annot.update()
                                    
                                except Exception as annot_error:
                                    try:
                                        # Method 3: Create invisible text layer using PDF operators
                                        # Insert text with rendering mode 3 (invisible)
                                        shape = page.new_shape()
                                        
                                        # Set text rendering mode to invisible (3)
                                        shape.insert_text(
                                            fitz.Point(rect.x0, rect.y1 - (original_height * 0.2)),
                                            text,
                                            fontsize=font_size,
                                            fontname="helv",
                                            render_mode=3  # Invisible text mode
                                        )
                                        
                                        # Commit the invisible text
                                        shape.commit()
                                        
                                    except Exception as shape_error:
                                        # Method 4: Last resort - create overlay without visible text
                                        try:
                                            # Create a completely transparent overlay
                                            overlay_rect = fitz.Rect(rect.x0, rect.y0, rect.x1, rect.y1)
                                            
                                            # Add text to document structure but make it invisible
                                            page.insert_textbox(
                                                overlay_rect,
                                                text,
                                                fontsize=font_size,
                                                fontname="helv",
                                                color=None,  # No color
                                                fill=None,   # No fill
                                                border_width=0,  # No border
                                                align=0
                                            )
                                            
                                        except:
                                            # Skip this text if all methods fail
                                            continue
                                            
            except Exception as page_error:
                logger.warning(f"Error processing page {page_num + 1}: {str(page_error)}")
                continue
        
        # Save with optimization
        doc.save(
            output_pdf_path, 
            garbage=4, 
            deflate=True, 
            clean=True,
            pretty=True,
            linearize=True
        )
        
        logger.info("PyMuPDF fallback completed with invisible text overlays")
        return True, "Success using invisible text overlays"
        
    except Exception as e:
        logger.error(f"Invisible overlay method failed: {str(e)}")
        return False, f"Invisible overlay method failed: {str(e)}"
    finally:
        if doc:
            doc.close()


def verify_pdf_has_selectable_text(pdf_path: str) -> tuple[bool, int]:
    """Verify that the PDF has selectable text and count characters"""
    try:
        doc = fitz.open(pdf_path)
        total_chars = 0
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text().strip()
            total_chars += len(text)
        
        doc.close()
        
        has_text = total_chars > 50
        logger.info(f"PDF verification: {total_chars} characters found, selectable: {has_text}")
        
        return has_text, total_chars
        
    except Exception as e:
        logger.error(f"Error verifying PDF: {str(e)}")
        return False, 0

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the HTML frontend"""
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Frontend file not found. Please ensure static/index.html exists.")

@app.post("/upload-pdf/")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload PDF and convert to searchable PDF with perfect text selection"""
    
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size must be less than 20MB")
    
    try:
        file_id = str(uuid.uuid4())[:8]
        input_filename = f"{file_id}_input.pdf"
        output_filename = f"{file_id}_searchable.pdf"
        
        input_path = UPLOAD_DIR / input_filename
        output_path = OUTPUT_DIR / output_filename
        
        with open(input_path, "wb") as f:
            f.write(content)
        
        logger.info(f"File uploaded: {input_filename} ({len(content)} bytes)")
        
        success, error_msg = create_searchable_pdf_with_ocrmypdf(str(input_path), str(output_path))
        
        if not success:
            logger.info("Trying pure text layer method...")
            success, error_msg = create_invisible_text_layer(str(input_path), str(output_path))
        
        if not success:
            try:
                os.remove(input_path)
            except:
                pass
            raise HTTPException(status_code=500, detail=f"All OCR methods failed: {error_msg}")
        
        if not output_path.exists():
            try:
                os.remove(input_path)
            except:
                pass
            raise HTTPException(status_code=500, detail="Processing completed but output file not found")
        
        has_selectable_text, char_count = verify_pdf_has_selectable_text(str(output_path))
        
        try:
            os.remove(input_path)
        except:
            pass
        
        return {
            "message": f"PDF processed successfully with perfect text selection ({error_msg})",
            "file_id": file_id,
            "original_filename": file.filename,
            "download_url": f"/download/{file_id}",
            "file_size": len(content),
            "has_selectable_text": has_selectable_text,
            "character_count": char_count,
            "processing_method": "OCRmyPDF",
            "strategy_used": error_msg
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing upload: {str(e)}")
        try:
            if 'input_path' in locals() and input_path.exists():
                os.remove(input_path)
            if 'output_path' in locals() and output_path.exists():
                os.remove(output_path)
        except:
            pass
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.get("/download/{file_id}")
async def download_pdf(file_id: str):
    """Download the processed searchable PDF"""
    
    output_filename = f"{file_id}_searchable.pdf"
    output_path = OUTPUT_DIR / output_filename
    
    if not output_path.exists():
        raise HTTPException(status_code=404, detail="File not found or has expired")
    
    return FileResponse(
        path=str(output_path),
        filename=f"searchable_{file_id}.pdf",
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=searchable_{file_id}.pdf"}
    )

@app.get("/health")
async def health_check():
    """Health check endpoint with dependency verification"""
    missing_deps = check_dependencies()
    
    status = "healthy" if not missing_deps else "degraded"
    message = "PDF OCR service is running" if not missing_deps else f"Missing dependencies: {', '.join(missing_deps)}"
    
    return {
        "status": status,
        "message": message,
        "dependencies": {
            "ocrmypdf": "ocrmypdf" not in missing_deps,
            "tesseract": "tesseract" not in missing_deps,
            "ghostscript": "ghostscript" not in missing_deps
        },
        "upload_dir": str(UPLOAD_DIR),
        "output_dir": str(OUTPUT_DIR)
    }

@app.delete("/cleanup/{file_id}")
async def cleanup_file(file_id: str):
    """Clean up processed files"""
    
    output_filename = f"{file_id}_searchable.pdf"
    output_path = OUTPUT_DIR / output_filename
    
    if output_path.exists():
        try:
            os.remove(output_path)
            return {"message": "File cleaned up successfully"}
        except Exception as e:
            logger.error(f"Error cleaning up file: {e}")
            return {"message": "Error cleaning up file", "error": str(e)}
    
    return {"message": "File not found or already cleaned up"}

@app.on_event("startup")
async def startup_event():
    """Check dependencies on startup"""
    logger.info("Starting PDF OCR Service v2.0...")
    
    static_dir = Path("static")
    if not static_dir.exists():
        logger.info("Creating static directory...")
        static_dir.mkdir(exist_ok=True)
    
    missing_deps = check_dependencies()
    
    if missing_deps:
        logger.warning(f"Missing dependencies: {', '.join(missing_deps)}")
        logger.warning("Service may not function properly.")
    else:
        logger.info("All dependencies are available!")
    
    logger.info(f"Upload directory: {UPLOAD_DIR}")
    logger.info(f"Output directory: {OUTPUT_DIR}")
    
    cleanup_old_files()

if __name__ == "__main__":
    import uvicorn
    
    port = int(os.environ.get("PORT", 8000))
    host = "0.0.0.0"
    
    logger.info(f"Starting server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
