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
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from paddleocr import PaddleOCR
import pytesseract
import uvicorn

app = FastAPI()

UPLOAD_DIR = Path.home() / "bill_uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
print(f"✅ Storage initialized at: {UPLOAD_DIR}")

OTHER_BACKEND_URL = "https://arcade-alan-tim-timothy.trycloudflare.com/process"

# ⭐ ADD YOUR WHATSAPP TOKEN HERE
WHATSAPP_ACCESS_TOKEN = "EAAMp9DvkixUBQqIZAk9q10D22kR8jjfWaWfZA6ezbHbmCbwnd1MIGM6BpcHwxoYd84uBMMhA6rwfSz2aKLaPAK6aOMw3dTzrtsA03yvvm99qIXcfXFZBiGJOzqfZAraJS3WHSibonef5LdNiEDMJJAB1iret0S0HZCZCQptwIUE4mlbHPHNe4dZBvByeJhHkolP3Xn5mF4gClnNH6OWrDOaspM9tRKWZCZCk3mVWhSGWLLH7D4T3rc4qKYIJZCfh94X7ep5LUru0idR8s1tpAuOFQWTZB8s"

# ⭐ VERIFY TOKEN — must match Meta dashboard
VERIFY_TOKEN = "ShlokaOCR"


# -------------------------------------------------------------------
# ⭐ WHATSAPP WEBHOOK VERIFICATION (THIS IS WHAT YOU WERE MISSING)
# -------------------------------------------------------------------
@app.get("/whatsapp/webhook")
async def verify_whatsapp_webhook(request: Request):

    params = request.query_params

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    print("Webhook verification attempt:", params)

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return int(challenge)

    return {"status": "verification failed"}


# --- INITIALIZE OCR ---
_paddle_ocr = PaddleOCR(
    lang="en",
    use_textline_orientation=True,
)

# -------------------------------------------------------------------
# OCR FUNCTION (UNCHANGED)
# -------------------------------------------------------------------
def extract_text_from_image(
    image_path: Path,
    confidence_threshold: float = 0.5,
    min_text_length: int = 10
) -> str:

    if not image_path.exists():
        raise FileNotFoundError(f"Image not found: {image_path}")

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

# -------------------------------------------------------------------
# ⭐ SHARED PIPELINE (USED BY BOTH FRONTENDS)
# -------------------------------------------------------------------
async def process_image_stream(file_stream):

    unique_id = str(uuid.uuid4())
    file_path = UPLOAD_DIR / f"{unique_id}.jpg"
    text_file_path = UPLOAD_DIR / f"{unique_id}.txt"

    # Save Image
    with file_path.open("wb") as buffer:
        shutil.copyfileobj(file_stream, buffer)

    # OCR Extraction
    extracted_content = extract_text_from_image(file_path)

    # Save TXT
    with open(text_file_path, "w", encoding="utf-8") as f:
        f.write(extracted_content)

    # Forward to orchestrator
    backend_response = None
    target_status = "Not Sent"

    try:
        with open(text_file_path, "rb") as f_to_send:

            payload_fields = {"bill_id": unique_id}
            payload_files = {
                "file": (text_file_path.name, f_to_send, "text/plain")
            }

            res = requests.post(
                OTHER_BACKEND_URL,
                data=payload_fields,
                files=payload_files,
                timeout=60
            )

            res.raise_for_status()
            target_status = "File Forwarded Successfully"
            backend_response = res.json()

    except requests.exceptions.HTTPError as e:
        print(f"Backend Error: {res.text}")
        target_status = f"Forwarding Failed: {str(e)}"
    except Exception as e:
        print(f"Connection error: {e}")
        target_status = f"Connection Failed: {str(e)}"

    return unique_id, target_status, backend_response

# -------------------------------------------------------------------
# FRONTEND 1 — EXISTING UI (UNCHANGED BEHAVIOUR)
# -------------------------------------------------------------------
@app.post("/upload")
async def handle_upload(file: UploadFile = File(...)):
    try:
        unique_id, target_status, backend_response = await process_image_stream(file.file)

        return {
            "status": "success",
            "unique_id": unique_id,
            "target_system_status": target_status,
            "orchestrator_data": backend_response
        }

    except Exception as e:
        print(f"Internal Server Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------------------------
# ⭐ FRONTEND 2 — WHATSAPP WEBHOOK
# -------------------------------------------------------------------
@app.post("/whatsapp/webhook")
async def whatsapp_webhook(req: Request):

    try:
        data = await req.json()

        message = data["entry"][0]["changes"][0]["value"]["messages"][0]

        if message["type"] != "image":
            return {"status": "ignored"}

        media_id = message["image"]["id"]

        headers = {"Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}"}

        # Step 1: Get Media URL
        meta_url = f"https://graph.facebook.com/v21.0/{media_id}"
        meta_res = requests.get(meta_url, headers=headers)
        media_url = meta_res.json()["url"]

        # Step 2: Download Image
        img_response = requests.get(media_url, headers=headers, stream=True)

        # Step 3: Send into SAME pipeline
        await process_image_stream(img_response.raw)

        return {"status": "ok"}

    except Exception as e:
        print("WhatsApp webhook error:", e)
        return {"status": "error"}

# -------------------------------------------------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
