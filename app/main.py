from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from contextlib import asynccontextmanager
from fastapi.staticfiles import StaticFiles
from datetime import datetime, timedelta, timezone
import requests
import logging
import traceback

# Services
from services.webhook_service import process_webhook, get_last_order_data
from services.iiko_service import get_payload, load_menu_from_iiko
from services.sync_service import update_amo_prices_with_iiko
from config import YANDEX_API_KEY

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logging.info("🚀 Server starting up… loading menu from iiko")
        load_menu_from_iiko()
        yield
    except Exception as e:
        logging.error(f"❌ Exception during application startup: {str(e)}")
        yield

app = FastAPI(lifespan=lifespan)

@app.get("/")
async def home():
    try:
        return {"message": "FastAPI is running!"}
    except Exception as e:
        logging.error(f"❌ Error in home endpoint: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
    
app.mount("/", StaticFiles(directory="app/static/build", html=True), name="static")

@app.get("/last-order")
async def get_last_order():
    """
    Returns the last parsed order from the global variable stored in webhook_service.
    """
    try:
        last_order = get_last_order_data()
        payload_iiko = get_payload()
        if last_order or payload_iiko:
            return {
                "last_order": last_order,
                "payload": payload_iiko
            }
        return {"message": "No order received yet"}
    except Exception as e:
        logging.error(f"❌ Error retrieving last order: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.post("/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Receives an AmoCRM webhook.  
    Immediately responds with JSON.  
    Processing occurs in the background.
    """
    try:
        logging.info("✅ Webhook received")
        raw_body = await request.body()
        decoded_body = raw_body.decode("utf-8")

        # Send an immediate "OK" response to AmoCRM
        response = JSONResponse(content={"status": "received"}, status_code=200)

        # Schedule background processing
        background_tasks.add_task(process_webhook, decoded_body, background_tasks)

        return response
    except Exception as e:
        logging.error(f"❌ Error processing webhook: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/update_menu_price")
async def update_menu_price():
    """
    Syncs product prices in AmoCRM catalog with prices from the current iiko menu.
    """
    try:
        result = update_amo_prices_with_iiko()
        return {"status": "completed", "updated": result}
    except Exception as e:
        logging.error(f"❌ Error updating menu prices: {str(e)}")
        return JSONResponse(content={"error": str(e)}, status_code=500)
    

YANDEX_BASE_URL = "https://b2b.taxi.yandex.net/b2b/cargo/integration/v2"

# Serve static files (React build)
app.mount("/", StaticFiles(directory="app/static/build", html=True), name="static")

@app.post("/api/calculate_price")
async def calculate_price(request: Request):
    data = await request.json()
    address = data.get("address")
    time_minutes = data.get("time")

    # Set due time
    due_time = datetime.now(timezone.utc) + timedelta(minutes=time_minutes)
    due = due_time.strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # Yandex API Request Body
    body = {
        "route_points": [
            {
                "id": 1,
                "coordinates": [71.423219, 51.128207],
                "fullname": "Казахстан, Астана, проспект Туран, 24, Italita",
                "country": "Казахстан",
                "city": "Астана",
                "street": "проспект Туран",
                "building": "24",
                "comment": "Ресторан Italita",
                "contact": {
                    "name": "Italita",
                    "phone": "+7 (778) 333 12 56"
                }
            },
            {
                "id": 2,
                "coordinates": [71.401911, 51.132355],
                "fullname": address,
                "country": "Казахстан",
                "city": "Астана",
                "street": address.split(',')[0],  # Extract street from address
                "building": address.split(',')[1] if ',' in address else "",
                "comment": "Получатель",
                "contact": {
                    "name": "Получатель",
                    "phone": "+7 (777) 777 77 77"
                }
            }
        ],
        "requirements": {
            "taxi_class": "courier",
            "cargo_options": ["thermobag"],
            "pro_courier": True,
            "door_to_door": True
        },
        "delivery_description": "Доставка готовой еды",
        "recipient_info": {
            "phone": "+7 (777) 777 77 77",
            "name": "Получатель"
        },
        "skip_door_to_door": False,
        "client_requirements": {
            "send_tracking_link": True,
            "cargo_loaders": 1
        },
        "due": due
    }

    headers = {
        "Authorization": f"Bearer {YANDEX_API_KEY}",
        "Accept-Language": "ru",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(f"{YANDEX_BASE_URL}/check-price", json=body, headers=headers)
        response.raise_for_status()
        price = response.json().get("offer", {}).get("price")
        return JSONResponse({"price": price})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    logging.error(f"❌ Validation error: {exc}")
    return JSONResponse(content={"error": "Invalid input data"}, status_code=422)

@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logging.error(f"❌ Unhandled exception: {traceback.format_exc()}")
    return JSONResponse(content={"error": "Internal server error"}, status_code=500)
