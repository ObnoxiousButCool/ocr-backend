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
            "📄 Image received! Processing your bill..."
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
