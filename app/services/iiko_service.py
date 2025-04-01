import requests
import logging
from app.config import (
    IIKO_API_KEY,
    IIKO_ORGANIZATION_ID,
    IIKO_TERMINAL_GROUP_ID,
    IIKO_MENU_ID,
    IIKO_BASE_URL,
    IIKO_MENU_URL
)
from typing import Optional, Dict, Tuple
import json
import time

from services.amocrm_service import add_note_to_amocrm

combo_mapping = {
    "1e2b0ce9-2c7a-4142-ab25-feb1bd703852": [
        {"productId": "9cf20e58-bea5-4348-93ca-cf38a8be6c15", "quantity": 1, "price": 0}
    ],
    "30efcd5d-b234-446d-9c1a-53dbfb359452": [
        {"productId": "49f605f8-2b60-4bb0-bf0a-f25ee5df30fb", "quantity": 1, "price": 0}
    ],
    "0b4a0d4c-1990-45f6-9dfd-e5db528663db": [
        {"productId": "df461857-fc28-45ca-8573-f76c416f8514", "quantity": 2, "price": 0},
        {"productId": "86b81e3c-257c-4375-a9aa-a96bdcb9f9e0", "quantity": 1, "price": 0, "sizeId": "70109d8e-3310-452b-b397-cab328ac4e70"},
        {"productId": "593c74a3-6afc-4351-944e-1ff28e6b38f3", "quantity": 1, "price": 0}
    ],
    "602dcb63-2ec1-4d2d-bd39-30b82b51c086": [
        {"productId": "df461857-fc28-45ca-8573-f76c416f8514", "quantity": 2, "price": 0},
        {"productId": "86b81e3c-257c-4375-a9aa-a96bdcb9f9e0", "quantity": 1, "price": 0, "sizeId": "70109d8e-3310-452b-b397-cab328ac4e70"},
        {"productId": "593c74a3-6afc-4351-944e-1ff28e6b38f3", "quantity": 1, "price": 0}
    ],
    "ee3b93f8-1aaa-4a19-b499-4049f27c94b8": [
        {"productId": "f3ba1253-184b-4864-8368-f0b0b93bc05b", "quantity": 2, "price": 0},
        {"productId": "a69398d3-0fe9-401b-8534-a1e84736e1fc", "quantity": 1, "price": 0, "sizeId": "70109d8e-3310-452b-b397-cab328ac4e70"},
        {"productId": "9d3c5448-b203-4cf5-aaa8-c851b155f618", "quantity": 1, "price": 0}
    ],
    "76349afd-be08-4175-9718-53417a7601c3": [
        {"productId": "f3ba1253-184b-4864-8368-f0b0b93bc05b", "quantity": 2, "price": 0},
        {"productId": "a69398d3-0fe9-401b-8534-a1e84736e1fc", "quantity": 1, "price": 0, "sizeId": "70109d8e-3310-452b-b397-cab328ac4e70"},
        {"productId": "9d3c5448-b203-4cf5-aaa8-c851b155f618", "quantity": 1, "price": 0}
    ],
    "ddfd96d2-e986-439c-8349-c3af4236301d": [
        {"productId": "de20e32a-bc30-46e8-8a0d-14fdc406cad9", "quantity": 2, "price": 0},
        {"productId": "e5af1312-dd4a-4fca-8632-f52fca48303e", "quantity": 1, "price": 0, "sizeId": "70109d8e-3310-452b-b397-cab328ac4e70"}
    ],
    "75ef6fb1-bfdc-4522-a86f-d7517edaa139": [
        {"productId": "20b3479c-6d91-4091-95b2-ee659890562b", "quantity": 1, "price": 0},
        {"productId": "6bad5be9-0269-4e45-b375-8c886a3849ec", "quantity": 1, "price": 0}
    ],
    "bd91e029-27fe-46b6-a90e-c74b91636082": [
        {"productId": "c9d00dba-d65c-472d-835c-83f174275b0d", "quantity": 1, "price": 0},
        {"productId": "eae50428-d917-4b55-89d0-fe0141bb0ac6", "quantity": 1, "price": 0}
    ]
}

payload_iiko = {}

_menu_lookup: Dict[Tuple[str, Optional[str]], dict] = {}

def get_iiko_token() -> Optional[str]:
    """Fetch authentication token from iiko API."""
    try:
        url = f"{IIKO_BASE_URL}/access_token"
        payload = {"apiLogin": IIKO_API_KEY}
        response = requests.post(url, json=payload)

        response.raise_for_status()
        return response.json().get("token")
    except requests.RequestException as e:
        logging.error(f"❌ Failed to fetch iiko token: {str(e)}")
        return None
    
def is_terminal_group_alive(lead_id) -> bool:
    """Check if the terminal group is alive."""
    try:
        token = get_iiko_token()
        if not token:
            return False

        headers = {"Authorization": f"Bearer {token}"}
        url = f"{IIKO_BASE_URL}/terminal_groups/is_alive"
        payload = {
            "organizationIds": [IIKO_ORGANIZATION_ID],
            "terminalGroupIds": [IIKO_TERMINAL_GROUP_ID]
        }

        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()

        is_alive_status = response.json().get("isAliveStatus", [])
        if is_alive_status and is_alive_status[0].get("isAlive"):
            logging.info(f"✅ Terminal group {IIKO_TERMINAL_GROUP_ID} is alive.")
            add_note_to_amocrm(lead_id, f"Терминал активен", "iiko")
            return True
        else:
            logging.error(f"❌ Terminal group {IIKO_TERMINAL_GROUP_ID} is not alive.")
            add_note_to_amocrm(lead_id, f"Терминал неактивен")
            return False
    except Exception as e:
        logging.error(f"❌ Error checking terminal group status: {str(e)}")
        add_note_to_amocrm(lead_id, f"Не удалось получить статус терминала", "iiko")
        return False

def load_menu_from_iiko():
    """Fetch and store the menu from the iiko API."""
    global _menu_lookup
    try:
        token = get_iiko_token()
        if not token:
            return

        headers = {"Authorization": f"Bearer {token}"}
        url = f"{IIKO_MENU_URL}/menu/by_id"
        body = {
            "externalMenuId": IIKO_MENU_ID,
            "organizationIds": [IIKO_ORGANIZATION_ID]
        }

        response = requests.post(url, headers=headers, json=body)
        response.raise_for_status()

        menu_data = response.json()
        for category in menu_data.get("itemCategories", []):
            for item in category.get("items", []):
                item_id = item.get("itemId")
                for size in item.get("itemSizes", []):
                    size_id = size.get("sizeId")
                    price_info = size.get("prices", [])[0] if size.get("prices") else None
                    key = (item_id, size_id if size_id else None)
                    _menu_lookup[key] = {
                        "name": item.get("name"),
                        "price": price_info["price"] if price_info else 0,
                        "organizationId": price_info["organizationId"] if price_info else IIKO_ORGANIZATION_ID
                    }
        logging.info(f"✅ Menu loaded from iiko with {len(_menu_lookup)} items")
    except Exception as e:
        logging.error(f"❌ Error loading menu from iiko: {str(e)}")

def get_menu_item(product_id: str, size_id: Optional[str] = None) -> Optional[dict]:
    try:
        key = (product_id, size_id if size_id else None)
        return _menu_lookup.get(key)
    except Exception as e:
        logging.error(f"❌ Error retrieving menu item: {str(e)}")
        return None

def create_iiko_order_from_amocrm(order: dict, lead_id: str) -> Optional[dict]:
    try:
        token = get_iiko_token()
        if not token:
            return None

        if not is_terminal_group_alive(lead_id):
            return None

        headers = {"Authorization": f"Bearer {token}"}
        items = []
        for item in order.get("menu", []):
            try:
                product_id = item.get("productId")
                size_id = item.get("sizeId")
                quantity = item.get("quantity", 1)

                menu_item = get_menu_item(product_id, size_id)
                if not menu_item:
                    continue

                item_payload = {
                    "productId": product_id,
                    "amount": float(quantity),
                    "price": menu_item["price"],
                    "type": "Product"
                }
                if size_id:
                    item_payload["productSizeId"] = size_id

                items.append(item_payload)

                # Check if the product is a combo and add associated items
                if product_id in combo_mapping:
                    for combo_item in combo_mapping[product_id]:
                        combo_size_id = combo_item.get("sizeId")
                        combo_item_payload = {
                            "productId": combo_item["productId"],
                            "amount": float(combo_item["quantity"]) * quantity,
                            "price": combo_item["price"],
                            "type": "Product"
                        }
                        if combo_size_id:
                            combo_item_payload["productSizeId"] = combo_size_id
                        items.append(combo_item_payload)
            except Exception as e:
                logging.warning(f"⚠️ Error processing item {item}: {str(e)}")

        if not items:
            return None

        # Payment mapping (update with actual IDs and types)
        payment_mapping = {
            "Kaspi bank": {
                "paymentTypeKind": "Card",
                "paymentTypeId": "012d5695-e609-4b51-9758-21f3791dee75"
            },
            "Наличные": {
                "paymentTypeKind": "Cash",
                "paymentTypeId": "09322f46-578a-d210-add7-eec222a08871"
            }
        }

        payment_method = order.get("payment_method", "Kaspi bank")
        payment_info = payment_mapping.get(payment_method, payment_mapping["Kaspi bank"])

        # Payment payload
        payments = [
            {
                "paymentTypeKind": payment_info["paymentTypeKind"],
                "sum": float(order.get("price", 0)),
                "paymentTypeId": payment_info["paymentTypeId"]
            }
        ]

        # Construct the customer payload
        customer = {
            "id": "",  # If customer ID is known, set it here
            "name": order.get("name"),
            "type": "one-time"
        }

        payload = {
            "organizationId": IIKO_ORGANIZATION_ID,
            "terminalGroupId": IIKO_TERMINAL_GROUP_ID,
            "order": {
                "orderTypeId": "5b1508f9-fe5b-d6af-cb8d-043af587d5c2",  # Update with actual order type ID
                "comment": order.get("comment"),
                "phone": "+" + order.get("phone"),
                "customer": customer,
                "items": items,
                "payments": payments
            }
        }

        global payload_iiko
        payload_iiko = payload

        # url = f"{IIKO_BASE_URL}/deliveries/create"
        # response = requests.post(url, json=payload, headers=headers)

        # # Check if the response is not successful
        # if response.status_code != 200:
        #     logging.error(f"❌ iiko order creation failed with status {response.status_code}: {response.text}")
        #     add_note_to_amocrm(lead_id, f"Ошибка создания заказа в iiko со статусом {response.status_code}: {response.text}", "iiko")
        #     return None

        # response.raise_for_status()

        # logging.info("✅ iiko order created successfully")
        # add_note_to_amocrm(lead_id, f"Заказ в iiko был успешно создан", "iiko")
        # return response.json()
    except Exception as e:
        logging.error(f"❌ Error creating iiko order: {str(e)}")
        add_note_to_amocrm(lead_id, f"Ошибка при создании заказа в iiko", "iiko")
        return None
    
def check_order_status(order_id: str) -> bool:
    """
    Check the status of the order before closing it.
    The status is considered valid for closing if 'creationStatus' is 'Success'.
    
    Parameters:
    - order_id (str): The ID of the order to check.

    Returns:
    - bool: True if the order can be closed, False otherwise.
    """
    token = get_iiko_token()
    if not token:
        logging.error("❌ No valid iiko token found to check the order status.")
        return False

    headers = {"Authorization": f"Bearer {token}"}
    
    # Prepare the payload for checking the order status
    payload = {
        "organizationId": IIKO_ORGANIZATION_ID,
        "orderIds": [order_id]
    }

    # Send request to check order status
    url = f"{IIKO_BASE_URL}/deliveries/by_id"
    response = requests.post(url, json=payload, headers=headers)

    if response.status_code == 200:
        order_info = response.json().get("orders", [])
        if order_info:
            order_status = order_info[0].get("creationStatus")
            if order_status == "Success":
                logging.info(f"✅ Order {order_id} is ready to be closed.")
                return True
            else:
                logging.error(f"❌ Order {order_id} cannot be closed, status is {order_status}.")
                return False
        else:
            logging.error(f"❌ No order information found for order ID {order_id}.")
            return False
    else:
        logging.error(f"❌ Failed to fetch order status for {order_id}: {response.status_code} - {response.text}")
        return False


def close_order_in_iiko(order_id: str, lead_id: str, cheque_additional_info: Optional[dict] = None) -> Optional[dict]:
    """
    Close the order in iiko system after ensuring that the order status is 'Success'.
    Uses adaptive waiting with retry logic to check the status before proceeding to close the order.

    Parameters:
    - order_id (str): The ID of the order to close.
    - cheque_additional_info (dict, optional): Optional info for the cheque, such as receipt information.
    """
    MAX_RETRIES = 10
    WAIT_TIME = 2  # Initial wait time in seconds

    # Retry logic with adaptive waiting
    for attempt in range(MAX_RETRIES):
        try:
            # Check the status of the order
            if check_order_status(order_id):
                logging.info(f"✅ Order {order_id} is ready to be closed.")
                break
            else:
                logging.warning(f"Attempt {attempt + 1}/{MAX_RETRIES}: Order {order_id} not ready to be closed.")
                time.sleep(WAIT_TIME)
                WAIT_TIME = min(WAIT_TIME * 2, 60)  # Exponential backoff
        except Exception as e:
            logging.error(f"❌ Error checking order status on attempt {attempt + 1}/{MAX_RETRIES}: {str(e)}")
            time.sleep(WAIT_TIME)
            WAIT_TIME = min(WAIT_TIME * 2, 60)  # Exponential backoff
    else:
        logging.error(f"❌ Order {order_id} could not be closed after {MAX_RETRIES} attempts.")
        return None

    try:
        # Proceed to close the order if status is 'Success'
        token = get_iiko_token()
        if not token:
            logging.error("❌ No valid iiko token found to close the order.")
            return None

        headers = {"Authorization": f"Bearer {token}"}

        # Construct the payload for closing the order
        payload = {
            "organizationId": IIKO_ORGANIZATION_ID,
            "orderId": order_id,
        }

        # Optionally include chequeAdditionalInfo if it's provided
        if cheque_additional_info:
            payload["chequeAdditionalInfo"] = cheque_additional_info

        # Sending request to close the order in iiko
        url = f"{IIKO_BASE_URL}/deliveries/close"
        response = requests.post(url, json=payload, headers=headers)

        # Check for HTTP errors
        response.raise_for_status()

        logging.info(f"✅ Order {order_id} successfully closed in iiko.")
        add_note_to_amocrm(lead_id, f"Заказ в iiko был успешно закрыт", "iiko")
        return response.json()
    except requests.RequestException as e:
        logging.error(f"❌ Failed to close order {order_id} in iiko: {str(e)}")
        add_note_to_amocrm(lead_id, f"Ошибка при закрытии заказа в iiko", "iiko")
        return None
    except Exception as e:
        logging.error(f"❌ Unexpected error while closing order {order_id}: {str(e)}")
        add_note_to_amocrm(lead_id, f"Непредвиденная ошибка при закрытии заказа в iiko", "iiko")
        return None

def get_payload():
    return payload_iiko