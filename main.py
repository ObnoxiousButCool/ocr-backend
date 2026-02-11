import os

os.environ['FLAGS_enable_pir_api'] = '0'
os.environ['FLAGS_enable_new_executor'] = '0'
os.environ["FLAGS_use_mkldnn"] = "0"    

import uuid
import shutil
import requests
import cv2
import numpy as np
from pathlib import Path
from PIL import Image
from fastapi import FastAPI, File, UploadFile, HTTPException
from paddleocr import PaddleOCR
import pytesseract
import uvicorn

app = FastAPI()

UPLOAD_DIR = Path.home() / "bill_uploads" 

# Ensure the folder is created inside your home directory
# This won't require 'sudo' because it's your personal  space
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
print(f"✅ Storage initialized at: {UPLOAD_DIR}")
OTHER_BACKEND_URL = "https://arcade-alan-tim-timothy.trycloudflare.com/process" 

# --- INITIALIZE OCR ---
_paddle_ocr = PaddleOCR(
    lang="en",
    use_textline_orientation=True,
)

def extract_text_from_image(
    image_path: Path,
    confidence_threshold: float = 0.5,
    min_text_length: int = 10
) -> str:
    """Extract text using PaddleOCR with Tesseract fallback."""
    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError("Failed to read image")

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # 1. Primary OCR: PaddleOCR
    # Note: Using .ocr() instead of .predict() for standard PaddleOCR usage
    result = _paddle_ocr.ocr(img_rgb, cls=True)
    
    paddle_lines = []
    if result and result[0]:
        for line in result[0]:
            text, score = line[1]
            if score >= confidence_threshold:
                paddle_lines.append(text)

    paddle_text = "\n".join(paddle_lines).strip()

    # Quality check
    if len(paddle_text) >= min_text_length:
        return paddle_text

    # 2. Fallback OCR: Tesseract
    pil_img = Image.fromarray(img_rgb).convert("L")
    is_scanned = np.array(pil_img).std() < 40

    if is_scanned:
        pil_img = pil_img.point(lambda x: 0 if x < 180 else 255, "1")
        tesseract_config = "--oem 3 --psm 3"
    else:
        tesseract_config = "--oem 3 --psm 6"

    tesseract_text = pytesseract.image_to_string(
        pil_img, 
        config=tesseract_config
    ).strip()

    fin_text = tesseract_text if len(tesseract_text) > len(paddle_text) else paddle_text
    print(f"Final extracted text:- {fin_text}")
    return fin_text

# --- API ENDPOINTS ---
# @app.post("/upload")
# async def handle_upload(file: UploadFile = File(...)):
#     try:
#         # 1. Generate ID and Save Image
#         unique_id = str(uuid.uuid4())
#         file_path = UPLOAD_DIR / f"{unique_id}.jpg"
        
#         with file_path.open("wb") as buffer:
#             shutil.copyfileobj(file.file, buffer)

#         # 2. Extract Text
#         extracted_content = extract_text_from_image(file_path)

#         # --- NEW: SAVE TO .TXT FILE ---
#         text_file_path = UPLOAD_DIR / f"{unique_id}.txt"
#         with open(text_file_path, "w", encoding="utf-8") as f:
#             f.write(extracted_content)
#         # ------------------------------

#         # 3. POST to the other backend
#         payload = {
#             "id": unique_id,
#             "text": extracted_content
#         }

#         try:
#             res = requests.post(OTHER_BACKEND_URL, json=payload, timeout=10)
#             res.raise_for_status()
#             target_status = "Forwarded Successfully"
#         except Exception as e:
#             target_status = f"Forwarding Failed: {str(e)}"

#         return {
#             "status": "success",
#             "unique_id": unique_id,
#             "text_saved_at": str(text_file_path), # Optional: let the frontend know
#             "target_system_status": target_status
#         }

#     except Exception as e:
#         print(f"Error: {e}")
#         raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload")
async def handle_upload(file: UploadFile = File(...)):
    try:
        # 1. Generate ID and local paths
        unique_id = str(uuid.uuid4())
        file_path = UPLOAD_DIR / f"{unique_id}.jpg"
        text_file_path = UPLOAD_DIR / f"{unique_id}.txt"
 
        # Save the original image
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
 
        # 2. Extract Text (Your existing OCR/Extraction logic)
        extracted_content = extract_text_from_image(file_path)
 
        # 3. Save Text File locally
        with open(text_file_path, "w", encoding="utf-8") as f:
            f.write(extracted_content)
 
        # 4. Forward to the NetSuite Orchestrator Backend
        try:
            with open(text_file_path, "rb") as f_to_send:
                # Key names must match the FastAPI backend arguments exactly:
                # bill_id: str = Form(...)
                # file: UploadFile = File(...)
                payload_fields = {"bill_id": unique_id}
                payload_files = {
                    "file": (text_file_path.name, f_to_send, "text/plain")
                }
 
                res = requests.post(
                    OTHER_BACKEND_URL,
                    data=payload_fields,
                    files=payload_files,
                    timeout=60  # Increased timeout for LLM processing
                )
                # If the backend returns 422, this will raise an exception with the detail
                res.raise_for_status()
                target_status = "File Forwarded Successfully"
                backend_response = res.json()
 
        except requests.exceptions.HTTPError as e:
            error_detail = res.json() if res.content else str(e)
            print(f"Backend Error: {error_detail}")
            target_status = f"Forwarding Failed: {error_detail}"
        except Exception as e:
            print(f"Connection error: {e}")
            target_status = f"Connection Failed: {str(e)}"
 
        return {
            "status": "success",
            "unique_id": unique_id,
            "target_system_status": target_status,
            "orchestrator_data": backend_response if target_status == "File Forwarded Successfully" else None
        }
 
    except Exception as e:
        print(f"Internal Server Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
