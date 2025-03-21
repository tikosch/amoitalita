from fastapi import FastAPI, Request
import json
import logging

app = FastAPI()

# Configure logging
logging.basicConfig(level=logging.INFO)


@app.get("/")
def home():
    return {"message": "FastAPI is running!"}


@app.post("/webhook")
async def receive_webhook(request: Request):
    payload = await request.json()
    
    # Log incoming request for debugging
    logging.info(f"Received Webhook: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    
    # Return a success response to AmoCRM
    return {"status": "Webhook received successfully", "data": payload}
