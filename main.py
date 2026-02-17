import os

os.environ['FLAGS_enable_pir_api'] = '0'
os.environ['FLAGS_enable_new_executor'] = '0'
<<<<<<< HEAD
os.environ["FLAGS_use_mkldnn"] = "0"    
=======
os.environ["FLAGS_use_mkldnn"] = "0"
>>>>>>> 3f559823c1e9385741a6075d1584db7407fc19a9

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
import logging

app = FastAPI()

UPLOAD_DIR = Path.home() / "bill_uploads" 

# Ensure the folder is created inside your home directory
# This won't require 'sudo' because it's your personal  space
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
print(f"✅ Storage initialized at: {UPLOAD_DIR}")
OTHER_BACKEND_URL = "https://arcade-alan-tim-timothy.trycloudflare.com/process" 

# --- INITIALIZE OCR ---
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from paddleocr import PaddleOCR
import pytesseract
import uvicorn

app = FastAPI()

UPLOAD_DIR = Path.home() / "bill_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
print(f"✅ Storage initialized at: {UPLOAD_DIR}")

OTHER_BACKEND_URL = "https://arcade-alan-tim-timothy.trycloudflare.com/process"

# -------------------------------------------------------------------
# ⭐ WHATSAPP CONFIG
# -------------------------------------------------------------------

WHATSAPP_ACCESS_TOKEN = "EAAMp9DvkixUBQqIZAk9q10D22kR8jjfWaWfZA6ezbHbmCbwnd1MIGM6BpcHwxoYd84uBMMhA6rwfSz2aKLaPAK6aOMw3dTzrtsA03yvvm99qIXcfXFZBiGJOzqfZAraJS3WHSibonef5LdNiEDMJJAB1iret0S0HZCZCQptwIUE4mlbHPHNe4dZBvByeJhHkolP3Xn5mF4gClnNH6OWrDOaspM9tRKWZCZCk3mVWhSGWLLH7D4T3rc4qKYIJZCfh94X7ep5LUru0idR8s1tpAuOFQWTZB8s"


VERIFY_TOKEN = "ShlokaOCR"
PHONE_NUMBER_ID = "1033580526497492"  # ⭐ ADD THIS FROM META DASHBOARD

# -------------------------------------------------------------------
# ⭐ SEND MESSAGE BACK TO WHATSAPP
# -------------------------------------------------------------------
def send_whatsapp_message(to_number: str, message_text: str):

    url = f"https://graph.facebook.com/v21.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "type": "text",
        "text": {"body": message_text}
    }

    try:
        r = requests.post(url, headers=headers, json=payload)
        print("WhatsApp reply:", r.text)
    except Exception as e:
        print("Failed sending WhatsApp message:", e)

# -------------------------------------------------------------------
# ⭐ WHATSAPP WEBHOOK VERIFICATION (GET)
# -------------------------------------------------------------------
@app.get("/whatsapp/webhook")
async def verify_whatsapp_webhook(request: Request):

    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)

    return {"status": "verification failed"}

# -------------------------------------------------------------------
# --- INITIALIZE OCR ---
# -------------------------------------------------------------------
_paddle_ocr = PaddleOCR(
    lang="en",
    use_textline_orientation=True,
)

lg = logging.getLogger("main")

# def extract_text_from_image(
#     image_path: Path,
#     confidence_threshold: float = 0.5,
#     min_text_length: int = 10
# ) -> str:
#     """Extract text using PaddleOCR with Tesseract fallback."""
#     if not image_path.exists():
#         raise FileNotFoundError(f"Image not found: {image_path}")

#     img = cv2.imread(str(image_path))
#     if img is None:
#         raise ValueError("Failed to read image")

#     img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

#     # 1. Primary OCR: PaddleOCR
#     # Note: Using .ocr() instead of .predict() for standard PaddleOCR usage
#     result = _paddle_ocr.ocr(img_rgb, cls=True)
    
#     paddle_lines = []
#     if result and result[0]:
#         for line in result[0]:
#             text, score = line[1]
#             if score >= confidence_threshold:
#                 paddle_lines.append(text)

#     paddle_text = "\n".join(paddle_lines).strip()

#     # Quality check
#     if len(paddle_text) >= min_text_length:
#         return paddle_text

#     # 2. Fallback OCR: Tesseract
#     pil_img = Image.fromarray(img_rgb).convert("L")
#     is_scanned = np.array(pil_img).std() < 40

#     if is_scanned:
#         pil_img = pil_img.point(lambda x: 0 if x < 180 else 255, "1")
#         tesseract_config = "--oem 3 --psm 3"
#     else:
#         tesseract_config = "--oem 3 --psm 6"

#     tesseract_text = pytesseract.image_to_string(
#         pil_img, 
#         config=tesseract_config
#     ).strip()

#     fin_text = tesseract_text if len(tesseract_text) > len(paddle_text) else paddle_text
#     print(f"Final extracted text:- {fin_text}")
#     return fin_text

import numpy as np

def extract_text_from_image(image_path: Path, confidence_threshold: float = 0.5) -> str:
    img = cv2.imread(str(image_path))
    result = _paddle_ocr.ocr(img, cls=True)
    
    if not result or not result[0]:
        return ""

    lines = []
    for line in result[0]:
        box = line[0]
        text = line[1][0]
        score = line[1][1]
        if score >= confidence_threshold:
            # Get center Y and start X
            y_center = sum([p[1] for p in box]) / 4
            x_start = box[0][0]
            lines.append({'y': y_center, 'x': x_start, 'text': text})

    # --- THE FIX: LINE SNAPPING ---
    # We round all Y coordinates to the nearest 15 pixels. 
    # This forces items on roughly the same line to have the EXACT same Y value.
    grid_size = 20 # Adjust this (15-25) based on how cramped the bill is
    for item in lines:
        item['y'] = round(item['y'] / grid_size) * grid_size

    # 1. Sort by the snapped Y, then by X
    lines.sort(key=lambda x: (x['y'], x['x']))

    # 2. Group by the snapped Y
    rows = {}
    for item in lines:
        y = item['y']
        if y not in rows:
            rows[y] = []
        rows[y].append(item)

    # 3. Build the text file with spatial padding
    final_output = []
    sorted_y_keys = sorted(rows.keys())
    
    for y in sorted_y_keys:
        row_items = rows[y]
        # Sort left to right
        row_items.sort(key=lambda x: x['x'])
        
        # Create a virtual canvas for the line
        line_canvas = [" "] * 100
        for item in row_items:
            # Map X (0-image_width) to 0-100 characters
            # Assuming image width is around 800-1000px
            char_pos = int(item['x'] / 10) 
            if char_pos < len(line_canvas):
                text = item['text']
                for i, char in enumerate(text):
                    if char_pos + i < len(line_canvas):
                        line_canvas[char_pos + i] = char
        
        final_output.append("".join(line_canvas).rstrip())

    return "\n".join(final_output)

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
# -------------------------------------------------------------------
# OCR FUNCTION
# -------------------------------------------------------------------
def extract_text_from_image(image_path: Path,
                            confidence_threshold: float = 0.5,
                            min_text_length: int = 10) -> str:

    img = cv2.imread(str(image_path))
    if img is None:
        raise ValueError("Failed to read image")

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    result = _paddle_ocr.ocr(img_rgb, cls=True)

    paddle_lines = []
    if result and result[0]:
        for line in result[0]:
            text, score = line[1]
            if score >= confidence_threshold:
                paddle_lines.append(text)

    paddle_text = "\n".join(paddle_lines).strip()

    if len(paddle_text) >= min_text_length:
        return paddle_text

    pil_img = Image.fromarray(img_rgb).convert("L")
    tesseract_text = pytesseract.image_to_string(
        pil_img, config="--oem 3 --psm 6"
    ).strip()

    return tesseract_text if len(tesseract_text) > len(paddle_text) else paddle_text

# -------------------------------------------------------------------
# ⭐ SHARED PIPELINE
# -------------------------------------------------------------------
async def process_image_stream(file_stream):

    unique_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{unique_id}.jpg"
    text_file_path = UPLOAD_DIR / f"{unique_id}.txt"

    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file_stream, buffer)

    extracted_content = extract_text_from_image(file_path)

    with open(text_file_path, "w", encoding="utf-8") as f:
        f.write(extracted_content)

    try:
        with open(text_file_path, "rb") as f_to_send:
            requests.post(
                OTHER_BACKEND_URL,
                data={"bill_id": unique_id},
                files={"file": (text_file_path.name, f_to_send, "text/plain")},
                timeout=60
            )
    except Exception as e:
        print("Forwarding error:", e)

# -------------------------------------------------------------------
# FRONTEND 1 — EXISTING UI
# -------------------------------------------------------------------
@app.post("/upload")
async def handle_upload(file: UploadFile = File(...)):
    try:
        await process_image_stream(file.file)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------------
# ⭐ FRONTEND 2 — WHATSAPP WEBHOOK (POST)
# -------------------------------------------------------------------
@app.post("/whatsapp/webhook")
async def whatsapp_webhook(req: Request):

    try:
        data = await req.json()
        message = data["entry"][0]["changes"][0]["value"]["messages"][0]

        if message["type"] != "image":
            return {"status": "ignored"}

        from_number = message["from"]

        # ⭐ Instant reply
        send_whatsapp_message(
            from_number,
            "📄 Image received! Processing your bill... Please check the dashboard in some time. Thank you! :)"
        )

        media_id = message["image"]["id"]
        headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}

        meta_url = f"https://graph.facebook.com/v21.0/{media_id}"
        media_url = requests.get(meta_url, headers=headers).json()["url"]

        img_response = requests.get(media_url, headers=headers, stream=True)

        await process_image_stream(img_response.raw)

        return {"status": "ok"}

    except Exception as e:
        print("WhatsApp webhook error:", e)
        return {"status": "error"}

# -------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
