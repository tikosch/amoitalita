import requests
import logging
import uuid
import time
import asyncio
from datetime import datetime, timedelta, timezone
from app.config import YANDEX_API_KEY, YANDEX_BASE_URL
from services.amocrm_service import update_lead_status_in_amocrm, add_note_to_amocrm

def format_phone(number):
    # Check if the number starts with '7' or '8' and drop the first digit
    if len(number) == 11 and (number.startswith("7") or number.startswith("8")):
        number = number[1:]
    return f"+7 {number[:3]} {number[3:6]} {number[6:8]} {number[8:]}"

def create_yandex_delivery(parsed_order, lead_id):
    """
    Creates a delivery order in Yandex using the parsed order from AmoCRM.
    """
    try:
        request_id = str(uuid.uuid4())
        url = f"{YANDEX_BASE_URL}/claims/create?request_id={request_id}"
        headers = {
            "Authorization": f"Bearer {YANDEX_API_KEY}",
            "Accept-Language": "ru",
            "Content-Type": "application/json"
        }

        courier_phone = format_phone(parsed_order.get("courier_phone"))
        customer_phone = format_phone(parsed_order.get("phone"))
        customer_name = parsed_order.get("name")

        address = parsed_order.get("address", "")
        parts = address.split(", ")

        street = parts[0] if len(parts) > 0 else ""
        building = parts[1] if len(parts) > 1 else ""
        porch = parts[2] if len(parts) > 2 else None
        floor = parts[3] if len(parts) > 3 else None
        apartment = parts[4] if len(parts) > 4 else None

        prep_time = int(parsed_order.get("prep_time", 0))
        due_time = datetime.now(timezone.utc) + timedelta(minutes=prep_time)
        due = due_time.strftime("%Y-%m-%dT%H:%M:%S+00:00")

        excluded_items = ["Кетчуп", "Сырный соус", "Острый соус", "Халапеньо", "Хлеб 4шт"]
        items = [
        {
            "title": item.get("name", "горячая еда"),
            "cost_currency": "KZT",
            "cost_value": str(item.get("price", 1)),
            "quantity": item.get("quantity", 1),
            "pickup_point": 1,
            "dropoff_point": 2
        }
        for item in parsed_order.get("menu", [])
        if item.get("name") not in excluded_items  # Exclude specified items
        ]

        route_point_2 = {
            "skip_confirmation": True,
            "point_id": 2,
            "type": "destination",
            "address": {
                "fullname": f"Казахстан, Астана, {street}, {building}" if porch is None else f"Казахстан, Астана, {street}, {building}, {porch}",
                "country": "Казахстан",
                "city": "Астана",
                "street": street,
                "building": building
            },
            "contact": {
                "name": customer_name,
                "phone": customer_phone
            },
            "visit_order": 2
        }

        if porch:
            route_point_2["address"]["porch"] = porch
        if floor:
            route_point_2["address"]["sfloor"] = floor
        if apartment:
            route_point_2["address"]["sflat"] = apartment

        order_data = {
            "items": items,
            "route_points": [
                {
                    "skip_confirmation": True,
                    "point_id": 1,
                    "type": "source",
                    "address": {
                        "fullname": "Казахстан, Астана, проспект Туран, 24, Italita",
                        "country": "Казахстан",
                        "city": "Астана",
                        "street": "проспект Туран",
                        "building": "24"
                    },
                    "comment": "Ресторан Italita",
                    "contact": {
                        "name": "Italita",
                        "phone": courier_phone
                    },
                    "visit_order": 1
                },
                route_point_2
            ],
            "client_requirements": {
                "taxi_class": "courier",
                "cargo_options": ["thermobag"],
                "pro_courier": False
            },
            "delivery_description": "Доставка горячей еды",
            "recipient_info": {
                "phone": customer_phone,
                "name": customer_name
            },
            "skip_door_to_door": False,
            "due": due,
            "auto_accept": False
        }

        response = requests.post(url, json=order_data, headers=headers)
        response.raise_for_status()
        logging.info("✅ Yandex delivery order created successfully.")
        add_note_to_amocrm(lead_id, "Заказ доставки успешно создан в Яндекс, ждем подтверждения", "Yandex")
        return response.json().get("id")

    except requests.RequestException as e:
        logging.error(f"❌ Network error while creating Yandex delivery: {str(e)}")
        add_note_to_amocrm(lead_id, f"Ошибка создания доставки в Яндекс", "Yandex")
        return None
    except Exception as e:
        logging.error(f"❌ Exception while creating Yandex delivery: {str(e)}")
        add_note_to_amocrm(lead_id, f"Ошибка при создании доставки в Яндекс", "Yandex")
        return None

def get_yandex_delivery_status(claim_id):
    """
    Retrieves the status of a Yandex delivery order.
    """
    try:
        url = f"{YANDEX_BASE_URL}/claims/info?claim_id={claim_id}"
        headers = {
            "Authorization": f"Bearer {YANDEX_API_KEY}",
            "Accept-Language": "ru"
        }
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        status = response.json().get("status")
        logging.info(f"ℹ️ Yandex delivery order status: {status}")
        return status
    except requests.RequestException as e:
        logging.error(f"❌ Network error while fetching Yandex delivery status: {str(e)}, response: {response.text}")
        return None
    except Exception as e:
        logging.error(f"❌ Unexpected error while fetching Yandex delivery status: {str(e)}")
        return None

def accept_yandex_delivery(claim_id, lead_id, version=1):
    """
    Accepts a Yandex delivery order.
    """
    try:
        url = f"{YANDEX_BASE_URL}/claims/accept?claim_id={claim_id}"
        headers = {
            "Authorization": f"Bearer {YANDEX_API_KEY}",
            "Accept-Language": "ru",
            "Content-Type": "application/json"
        }
        response = requests.post(url, json={"version": version}, headers=headers)
        response.raise_for_status()
        logging.info(f"🚚 Delivery {claim_id} has been accepted.")
        add_note_to_amocrm(lead_id, f"Доставка успешно подтверждена, ожидаем курьера...", "Yandex")
        yandex_cargo_link = "https://delivery.yandex.kz/account/cargo"
        add_note_to_amocrm(lead_id, f"🔗 Ссылка для отслеживания на Yandex Cargo: {yandex_cargo_link}")
        logging.info(f"🔗 Yandex Cargo tracking link sent: {yandex_cargo_link}")
        return True
    except requests.RequestException as e:
        logging.error(f"❌ Network error while accepting Yandex delivery: {str(e)}")
        return False
    except Exception as e:
        logging.error(f"❌ Exception while accepting Yandex delivery: {str(e)}")
        return False

def get_yandex_tracking_links(claim_id):
    """
    Retrieves tracking links for the Yandex delivery order.
    Returns the tracking links if available, otherwise None.
    """
    url = f"{YANDEX_BASE_URL}/claims/tracking_links?claim_id={claim_id}"
    headers = {
        "Authorization": f"Bearer {YANDEX_API_KEY}",
        "Accept-Language": "ru"
    }

    try:
        response = requests.get(url, headers=headers)
        response_data = response.json()
        tracking_links = response_data.get("tracking_links")
        if tracking_links:
            logging.info("✅ Yandex tracking links retrieved successfully.")
            return tracking_links
        else:
            logging.warning("⚠️ No tracking links available for the given claim_id.")
            return None
    except Exception as e:
        logging.error(f"❌ Exception while fetching Yandex tracking links: {str(e)}")
        return None
    
async def track_yandex_delivery(claim_id, lead_id):
    MAX_RETRIES = 20
    WAIT_TIME = 60

    for attempt in range(MAX_RETRIES):
        try:
            status = get_yandex_delivery_status(claim_id)

            # Fetch courier info if the status indicates a courier is assigned or in progress
            if status in ["performer_found", "pickup_arrived", "pickup_finished", "delivering"]:
                logging.info(f"✅ Status '{status}' for delivery {claim_id}. Attempting to get courier info.")
                add_note_to_amocrm(lead_id, f"Обновленный статус доставки: {status}. Получаем данные курьера.", "Yandex")
                yandex_response = get_yandex_claim_info(claim_id)
                if yandex_response:
                    courier_info = get_courier_info(claim_id, yandex_response)
                    add_note_to_amocrm(lead_id, f"Курьер: {courier_info['courier_name']}, Телефон: {courier_info['courier_phone']}, Ожидание: {courier_info['eta_minutes']} мин", "Yandex")
                else:
                    logging.warning(f"⚠️ Failed to get courier info for delivery {claim_id}")
                    add_note_to_amocrm(lead_id, "Не удалось получить данные курьера", "Yandex")

            # Check for final delivery completion
            if status == "delivered_finish":
                logging.info(f"✅ Delivery {claim_id} has been completed.")
                add_note_to_amocrm(lead_id, f"Доставка {claim_id} завершена", "Yandex")
                update_lead_status_in_amocrm(lead_id, 142)  # Status "Closed"
                return True

            elif status:
                logging.info(f"🚚 Current status of delivery {claim_id}: {status}")
            else:
                logging.warning(f"⚠️ Could not fetch status for delivery {claim_id} on attempt {attempt + 1}.")

            await asyncio.sleep(WAIT_TIME)
        except Exception as e:
            logging.error(f"❌ Exception while tracking Yandex delivery: {str(e)}")
            add_note_to_amocrm(lead_id, f"Ошибка при отслеживании доставки Яндекс: {str(e)}", "Yandex")

    logging.error(f"❌ Failed to confirm delivery completion for {claim_id} after {MAX_RETRIES} attempts.")
    add_note_to_amocrm(lead_id, f"Не удалось подтвердить завершение доставки после {MAX_RETRIES} попыток", "Yandex")
    return False

    
def get_courier_phone(claim_id: str, point_id: int) -> str:
    """
    Retrieves the phone number of the courier via the driver-voiceforwarding endpoint.
    """
    try:
        url = f"{YANDEX_BASE_URL}/driver-voiceforwarding"
        headers = {
            "Authorization": f"Bearer {YANDEX_API_KEY}",
            "Accept-Language": "ru",
            "Content-Type": "application/json"
        }
        payload = {
            "claim_id": claim_id,
            "point_id": point_id
        }

        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        phone_data = response.json()

        phone_number = phone_data.get("phone", "Unknown")
        extension = phone_data.get("ext", "")

        if extension:
            phone_number += f" доб. {extension}"

        logging.info(f"✅ Courier phone number retrieved: {phone_number}")
        return phone_number

    except requests.RequestException as e:
        logging.error(f"❌ Network error while fetching courier phone: {str(e)}")
        return "Unknown"
    except Exception as e:
        logging.error(f"❌ Unexpected error while fetching courier phone: {str(e)}")
        return "Unknown"
    
def get_courier_info(claim_id: str, response_data: dict) -> dict:
    """
    Extracts the courier information from the Yandex delivery response.
    """
    try:
        performer_info = response_data.get("performer_info", {})
        courier_name = performer_info.get("courier_name", "Unknown")
        current_point_id = response_data.get("current_point_id")

        # Check if current_point_id exists and find the corresponding route point
        point_id = None
        if current_point_id:
            route_points = response_data.get("route_points", [])
            for point in route_points:
                if point.get("id") == current_point_id:
                    point_id = point.get("id")
                    break
        
        if not point_id:
            logging.error(f"❌ No matching route point found for current_point_id: {current_point_id}")
            point_id = 0

        # Fetch courier phone using the helper function
        courier_phone = get_courier_phone(claim_id, point_id)

        # Extract the 'due' field and calculate minutes to arrival
        due_str = response_data.get("due")
        if due_str:
            try:
                due_time = datetime.fromisoformat(due_str.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                minutes_to_arrival = int((due_time - now).total_seconds() / 60)
                if minutes_to_arrival < 0:
                    minutes_to_arrival = 0
            except Exception as e:
                logging.error(f"❌ Error parsing 'due' time: {str(e)}")
                minutes_to_arrival = "Unknown"
        else:
            minutes_to_arrival = "Unknown"

        pricing = response_data.get("pricing", {}).get("offer", {})
        price = float(pricing.get("price", 0)) or float(pricing.get("price_raw", 0))
        currency = response_data.get("pricing", {}).get("currency", "KZT")
        formatted_price = format_price(price, currency)

        logging.info(f"✅ Courier info: Name: {courier_name}, Phone: {courier_phone}, ETA: {minutes_to_arrival} minutes, Price: {formatted_price}")

        return {
            "courier_name": courier_name,
            "courier_phone": courier_phone,
            "eta_minutes": minutes_to_arrival,
            "price": formatted_price
        }

    except Exception as e:
        logging.error(f"❌ Error extracting courier info: {str(e)}")
        return {
            "courier_name": "Unknown",
            "courier_phone": "Unknown",
            "eta_minutes": "Unknown",
            "price": "Unknown Price"
        }
    
def get_yandex_claim_info(claim_id: str) -> dict:
    try:
        url = f"{YANDEX_BASE_URL}/claims/info?claim_id={claim_id}"
        headers = {
            "Authorization": f"Bearer {YANDEX_API_KEY}",
            "Accept-Language": "ru"
        }
        response = requests.post(url, headers=headers)
        response.raise_for_status()
        logging.info(f"✅ Successfully fetched claim info for {claim_id}")
        return response.json()
    except requests.RequestException as e:
        logging.error(f"❌ Network error while fetching claim info: {str(e)}")
        return {}
    except Exception as e:
        logging.error(f"❌ Unexpected error while fetching claim info: {str(e)}")
        return {}
    
def format_price(price: float, currency: str = "KZT") -> str:
    """
    Formats the price for display in AmoCRM.
    """
    try:
        return f"{round(price, 2)} {currency}"
    except Exception as e:
        logging.error(f"❌ Error formatting price: {str(e)}")
        return "Unknown Price"

def track_yandex_delivery_sync(claim_id, lead_id):
    MAX_RETRIES = 180      # e.g. 20 attempts
    WAIT_TIME = 30        # e.g. 60 seconds between checks
    have_tracking_links = False
    courier_info_fetched = False
    last_status = None

    for attempt in range(MAX_RETRIES):
        try:
            # Fetch the current status once per iteration
            status = get_yandex_delivery_status(claim_id)
            
            # Log the status change (or any new status if first iteration)
            if status and status != last_status:
                logging.info(f"🚚 Status changed to '{status}' for claim {claim_id}.")
                status_message = get_status_message_russian(status)
                add_note_to_amocrm(lead_id, f"Статус доставки изменен: {status_message}", "Yandex")
                last_status = status

            if not have_tracking_links:
                    links = get_yandex_tracking_links(claim_id)
                    if links:
                        have_tracking_links = True
                        for link in links:
                            add_note_to_amocrm(lead_id, f"🔗 Ссылка для отслеживания заказа: {link}")
                        logging.info(f"🚚 Tracking links found: {links}")

            if not courier_info_fetched and status in ["performer_found", "pickup_arrived", "pickuped"]:
                    yandex_response = get_yandex_claim_info(claim_id)
                    if yandex_response:
                        courier_info = get_courier_info(claim_id, yandex_response)
                        add_note_to_amocrm(
                            lead_id,
                            f"Курьер: {courier_info['courier_name']}, Телефон: {courier_info['courier_phone']}, "
                            f"Прибытие через: {courier_info['eta_minutes']} мин"
                        )
                        courier_info_fetched = True
            
            if status == "delivered_finish":
                logging.info(f"✅ Delivery {claim_id} completed.")
                add_note_to_amocrm(lead_id, f"Доставка {claim_id} завершена", "Yandex")
                return True
                
            if status == "cancelled_by_taxi":
                logging.warning(f"❌ Cancelled by taxi driver: {claim_id}. Checking if auto-resumed.")
                add_note_to_amocrm(lead_id, f"Доставка отменена курьером: {claim_id}", "Yandex")
                time.sleep(WAIT_TIME)
                continue  # Check if the status changes

            if status in ["returning", "return_arrived"]:
                logging.info(f"🔄 Returning package: {claim_id}.")
                add_note_to_amocrm(lead_id, f"Возврат товара в процесс: {claim_id}", "Yandex")

            if status in ["returned", "returned_finish"]:
                logging.info(f"🔁 Return completed: {claim_id}.")
                add_note_to_amocrm(lead_id, f"Возврат завершен: {claim_id}", "Yandex")
                return False

            # Log any failure to fetch status
            if status is None:
                logging.warning(f"⚠️ Could not fetch status for delivery {claim_id}, attempt {attempt+1} of {MAX_RETRIES}.")

            # Sleep before the next retry
            time.sleep(WAIT_TIME)

        except Exception as e:
            logging.error(f"❌ Error in track_yandex_delivery_sync: {e}")
            add_note_to_amocrm(lead_id, f"Ошибка отслеживания доставки Яндекс: {str(e)}", "Yandex")
            continue

    # If we exit the loop without successful completion
    logging.error(f"❌ Delivery {claim_id} was not completed after {MAX_RETRIES} checks.")
    add_note_to_amocrm(lead_id, f"Доставка не завершена после {MAX_RETRIES} попыток.", "Yandex")
    return False

def try_accept_yandex_delivery(claim_id, lead_id, retries=5, wait_time=2):
    for attempt in range(retries):
        try:
            status = get_yandex_delivery_status(claim_id)
            if status == "ready_for_approval":
                if accept_yandex_delivery(claim_id, lead_id):
                    return True
            elif status in ["performer_lookup", "performer_found"]:
                return True
            time.sleep(wait_time)
        except Exception as e:
            logging.error(f"❌ Error accepting Yandex delivery: {str(e)}")
    return False

def get_status_message_russian(status):
    status_messages = {
        "new": "Создана новая заявка.",
        "estimating": "Идет процедура оценки заявки: подбор типа автомобиля по параметрам товара и расчет стоимости.",
        "ready_for_approval": "Заявка успешно оценена и ожидает подтверждения.",
        "accepted": "Заявка подтверждена.",
        "performer_lookup": "Идет поиск курьера для заказа.",
        "performer_draft": "Производится поиск курьера в соответствии с указанными в заявке требованиями.",
        "performer_found": "Курьер найден и едет к отправителю (точка А).",
        "pickup_arrived": "Курьер приехал в точку А, чтобы забрать заказ.",
        "ready_for_pickup_confirmation": "Курьер ждет, когда отправитель назовет ему код подтверждения.",
        "pickuped": "Курьер подтвердил получение товара.",
        "delivery_arrived": "Курьер приехал к получателю (точка Б).",
        "ready_for_delivery_confirmation": "Курьер готов передать товар получателю. Ожидание кода подтверждения.",
        "pay_waiting": "Заказ ожидает оплаты.",
        "delivered": "Курьер передал товар получателю. Доставка подтверждена.",
        "delivered_finish": "Доставка завершена. Курьер доставил все товары.",
        "returning": "Курьер возвращает товар отправителю.",
        "return_arrived": "Курьер приехал в точку возврата.",
        "ready_for_return_confirmation": "Курьер ждет код подтверждения на точке возврата.",
        "returned": "Курьер вернул товар отправителю. Возврат товара подтвержден.",
        "returned_finish": "Заказ завершен с возвратом товара.",
        "cancelled_by_taxi": "Заказ отменен курьером до получения товара.",
        "failed": "Ошибка при подтверждении заявки. Создайте новую заявку."
    }
    return status_messages.get(status, f"Неизвестный статус доставки: {status}")
