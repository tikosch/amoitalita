import logging
import traceback
import asyncio
import time
from urllib.parse import parse_qs
from datetime import datetime, timedelta, timezone
from fastapi import BackgroundTasks

from services.amocrm_service import get_lead_data, update_lead_status_in_amocrm, add_note_to_amocrm, get_child_lead_id
from services.iiko_service import create_iiko_order_from_amocrm, get_menu_item, close_order_in_iiko
from services.yandex_service import create_yandex_delivery, get_yandex_delivery_status, get_yandex_tracking_links, accept_yandex_delivery, track_yandex_delivery_sync, try_accept_yandex_delivery
from app.config import AMOCRM_DOMAIN, AMOCRM_TOKEN
import requests

# Global variable to store the last parsed order (for /last-order endpoint)
last_order = {}

def extract_field(custom_fields, name):
    try:
        for field in custom_fields:
            if field.get("field_name") == name:
                values = field.get("values", [])
                # If there are multiple values, join them with a comma
                if len(values) > 1:
                    return ", ".join([str(value.get("value", "")) for value in values])
                elif values:
                    return values[0].get("value", "")
        return None
    except Exception as e:
        logging.error(f"❌ Error extracting field '{name}': {str(e)}")
        return None


def get_current_time():
    try:
        current_time = datetime.now(timezone.utc) + timedelta(hours=5)
        return current_time.strftime("%H%M")
    except Exception as e:
        logging.error(f"❌ Error getting current time: {str(e)}")
        return "0000"

def parse_lead(lead: dict, child_lead_id):
    """
    Parses a lead from AmoCRM to extract order information and iiko menu items.
    Products must have custom field 'productId' and optionally 'sizeId'.
    """
    try:
        custom_fields = lead.get("custom_fields_values", [])

        parsed_data = {
            "order_id": lead.get("id"),
            "price": lead.get("price"),
            "order_num": get_current_time(), 
            "name": extract_field(custom_fields, "ФИО"),
            "phone": extract_field(custom_fields, "Номер клиента"),
            "courier_phone": extract_field(custom_fields, "Номер Italita"),
            "address": extract_field(custom_fields, "Адрес"),
            "comment": extract_field(custom_fields, "Комментарий к заказу"),
            "branch": extract_field(custom_fields, "Филиал"),
            "source": extract_field(custom_fields, "Источник"),
            "payment_method": extract_field(custom_fields, "Способ оплаты"),
            "prep_time": extract_field(custom_fields, "Время приготовления"),
            "menu": []
        }

        update_lead_name(child_lead_id, f"{parsed_data['name']} + {get_current_time()}")

        total_price = 0.0
        menu_items = []

        for product in lead.get("_embedded", {}).get("products", []):
            try:
                product_id = product.get("productId")
                size_id = product.get("sizeId")
                quantity = product.get("quantity", 1)

                if not product_id:
                    logging.warning("⚠️ Skipping product without productId")
                    add_note_to_amocrm(child_lead_id, "Продукт без productId пропущен", "amoCRM")
                    continue

                menu_item = get_menu_item(product_id, size_id)
                if not menu_item:
                    logging.warning(f"❌ No matching menu item for productId={product_id}, sizeId={size_id}")
                    add_note_to_amocrm(child_lead_id, f"Нет соответствующего пункта меню для productId={product_id}, sizeId={size_id}", "amoCRM")
                    continue

                line_total = menu_item["price"] * quantity
                total_price += line_total

                menu_items.append({
                    "productId": product_id,
                    "sizeId": size_id,
                    "name": menu_item["name"],
                    "price": menu_item["price"],
                    "quantity": quantity,
                    "line_total": line_total
                })

            except Exception as e:
                logging.error(f"❌ Error parsing product: {str(e)}")
                add_note_to_amocrm(child_lead_id, f"Ошибка при парсинге продукта", "amoCRM")

        parsed_data["menu"] = menu_items
        parsed_data["price"] = total_price
        return parsed_data

    except Exception as e:
        logging.error(f"❌ Error parsing lead: {str(e)}")
        add_note_to_amocrm(child_lead_id, f"Ошибка при парсинге сделки", "amoCRM")
        return {}


def update_lead_price(lead_id: int, new_price: float):
    """
    Updates the 'price' field of the lead in AmoCRM.
    """
    try:
        url = f"https://{AMOCRM_DOMAIN}/api/v4/leads"
        headers = {
            "Authorization": f"Bearer {AMOCRM_TOKEN}",
            "Content-Type": "application/json"
        }

        payload = [{
            "id": int(lead_id),
            "price": int(new_price)
        }]

        response = requests.patch(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise an exception for HTTP errors
        logging.info(f"✅ Updated lead {lead_id} price to {new_price}")

    except requests.RequestException as e:
        logging.error(f"❌ Network error while updating lead {lead_id} price: {str(e)}")
    except Exception as e:
        logging.error(f"❌ Could not update lead {lead_id} price: {str(e)}")


def update_lead_name(lead_id: int, new_name: str):
    """
    Updates the 'name' field of the lead in AmoCRM.
    """
    try:
        url = f"https://{AMOCRM_DOMAIN}/api/v4/leads"
        headers = {
            "Authorization": f"Bearer {AMOCRM_TOKEN}",
            "Content-Type": "application/json"
        }
        payload = [{
            "id": int(lead_id),
            "name": new_name,
            "custom_fields_values": [
                {
                    "field_id": 416863,
                    "values": [
                        {
                            "value": get_current_time()
                        }
                    ]
                }
            ]
        }]

        response = requests.patch(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise an exception for HTTP errors
        logging.info(f"✅ Lead {lead_id} name updated to {new_name}")

    except requests.RequestException as e:
        logging.error(f"❌ Network error while updating lead {lead_id} name: {str(e)}")
    except Exception as e:
        logging.error(f"❌ Could not update lead {lead_id} name: {str(e)}")

def process_webhook(decoded_body: str, background_tasks: BackgroundTasks):
    """
    Processes an incoming webhook from AmoCRM in the background.
    """
    try:
        logging.info(f"🔹 Raw Webhook: {decoded_body}")
        parsed = parse_qs(decoded_body)

        lead_id = (
            parsed.get("leads[add][0][id]", [None])[0]
            or parsed.get("leads[status][0][id]", [None])[0]
        )

        if not lead_id:
            logging.warning("❌ No lead ID found in webhook")
            return

        child_lead_id = get_child_lead_id(lead_id)

        lead_data = get_lead_data(lead_id)
        if not lead_data:
            logging.error("❌ Lead data missing")
            add_note_to_amocrm(child_lead_id, "Данные сделки отсутствуют", "amoCRM")
            return

        parsed_order = parse_lead(lead_data, child_lead_id)
        if not parsed_order.get("menu"):
            logging.error("❌ No valid menu items parsed — nothing to send to iiko")
            add_note_to_amocrm(child_lead_id, "Нет корректных пунктов меню для отправки в iiko", "amoCRM")
            return

        global last_order
        last_order = parsed_order

        update_lead_price(child_lead_id, parsed_order["price"])

        formatted_message = format_order_message(last_order)
        add_note_to_amocrm(child_lead_id, formatted_message)
        
        iiko_response = create_iiko_order_from_amocrm(parsed_order, child_lead_id)
        order_id = iiko_response.get("orderInfo", {}).get("id")

        if not order_id:
            logging.error("❌ No orderId found in iiko response")
            add_note_to_amocrm(child_lead_id, "Не удалось найти orderId в ответе от iiko", "iiko")
            return
        logging.info(f"✅ iiko order {order_id} created successfully.")
        add_note_to_amocrm(child_lead_id, f"Заказ {order_id} успешно создан в iiko.", "iiko")

        close_order_in_iiko(order_id, child_lead_id)
        logging.info(f"✅ iiko order {order_id} closed successfully.")
        add_note_to_amocrm(child_lead_id, f"Заказ {order_id} успешно завершен в iiko.", "iiko")

        claim_id = create_yandex_delivery(parsed_order, child_lead_id)
        if not claim_id:
            logging.error("❌ Failed to create Yandex delivery order")
            add_note_to_amocrm(child_lead_id, "Не удалось создать заказ на доставку в Яндекс", "Yandex")
            return

        if not try_accept_yandex_delivery(claim_id, child_lead_id):
            log_and_note(child_lead_id, "Ошибка при принятии доставки Яндекс", "Yandex")
            return
        
        background_tasks.add_task(track_yandex_delivery_sync, claim_id, child_lead_id)
        log_and_note(child_lead_id, f"Начато отслеживание доставки Яндекс с claim_id: {claim_id}", "Yandex")

    except Exception as e:
        logging.error(f"❌ Error in process_webhook: {traceback.format_exc()}")
        log_and_note(child_lead_id, "Ошибка в процессе обработки вебхука", "amoCRM")


def get_last_order_data():
    """
    Returns the most recent parsed order for the /last-order endpoint.
    """
    try:
        return last_order
    except Exception as e:
        logging.error(f"❌ Error getting last order data: {str(e)}")
        return {}

def format_order_message(order: dict) -> str:
    """
    Formats the last order into a comprehensive message for AmoCRM.
    """
    try:
        message = f"🔔 Новый заказ от клиента:\n"
        message += f"🆔 Заказ №: {order.get('order_num', 'N/A')}\n"
        message += f"👤 Имя клиента: {order.get('name', 'N/A')}\n"
        message += f"📞 Телефон клиента: {order.get('phone', 'N/A')}\n"
        message += f"🏠 Адрес: {order.get('address', 'N/A')}\n"
        message += f"💬 Комментарий: {order.get('comment', 'Нет комментария')}\n"
        message += f"🏢 Филиал: {order.get('branch', 'N/A')}\n"
        message += f"💳 Способ оплаты: {order.get('payment_method', 'N/A')}\n"
        message += f"🕰 Время приготовления: {order.get('prep_time', 'N/A')} минут\n"
        message += f"📦 Источник: {order.get('source', 'N/A')}\n"
        message += f"💰 Общая стоимость: {round(order.get('price', 0), 2)} KZT\n\n"

        message += "🍽️ Меню:\n"
        for item in order.get("menu", []):
            item_name = item.get("name", "Неизвестное блюдо")
            quantity = item.get("quantity", 1)
            price = round(item.get("price", 0), 2)
            line_total = round(item.get("line_total", 0), 2)
            message += f"  - {item_name} x{quantity} ({price} KZT) = {line_total} KZT\n"

        return message
    except Exception as e:
        logging.error(f"❌ Error formatting order message: {str(e)}")
        return "Ошибка формирования заказа для отправки"
    
def log_and_note(lead_id, message, service):
    logging.info(f"{service}: {message}")
    add_note_to_amocrm(lead_id, message, service)