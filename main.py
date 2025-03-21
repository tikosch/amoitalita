from fastapi import FastAPI, Request, Form
from fastapi.responses import JSONResponse
import json
import logging
import traceback
from urllib.parse import parse_qs, unquote

app = FastAPI()
logging.basicConfig(level=logging.INFO)

@app.get("/")
def home():
    return {"message": "FastAPI is running!"}

@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        content_type = request.headers.get("content-type", "")
        raw_body = await request.body()
        decoded_body = raw_body.decode("utf-8")

        logging.info(f"Raw Webhook Body: {decoded_body}")
        
        # Try JSON first
        if "application/json" in content_type:
            payload = await request.json()
        else:
            # It's form-urlencoded: parse it
            parsed_data = parse_qs(decoded_body)
            # Flatten the structure for logging/debugging
            payload = {k: v[0] if len(v) == 1 else v for k, v in parsed_data.items()}
        
        logging.info(f"Parsed Webhook Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
        return {"status": "Webhook received", "data": payload}
    
    except Exception as e:
        logging.error(f"Error processing webhook: {traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"error": str(e)})
