from fastapi import FastAPI, Request
import json
import logging
import traceback

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)

@app.get("/")
def home():
    return {"message": "FastAPI is running!"}

@app.post("/webhook")
async def receive_webhook(request: Request):
    try:
        # Read the raw request body
        raw_body = await request.body()
        logging.info(f"Raw Webhook Body: {raw_body.decode('utf-8')}")

        # Try to parse JSON
        payload = await request.json()
        logging.info(f"Received Webhook: {json.dumps(payload, indent=2, ensure_ascii=False)}")

        return {"status": "Webhook received successfully", "data": payload}
    
    except Exception as e:
        # Log the full error traceback
        logging.error(f"Error processing webhook: {traceback.format_exc()}")

        return {"status": "error", "message": str(e)}
