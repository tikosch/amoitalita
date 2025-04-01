import requests
import logging
from app.config import (
    AMOCRM_DOMAIN,
    AMOCRM_TOKEN,
    AMOCRM_CATALOG_ID
)
from services.iiko_service import get_menu_item

def fetch_catalog_elements():
    """Fetch all catalog elements (paginated) from AmoCRM."""
    elements = []
    page = 1

    while True:
        try:
            url = f"https://{AMOCRM_DOMAIN}/api/v4/catalogs/{AMOCRM_CATALOG_ID}/elements?page={page}&limit=250"
            headers = {
                "Authorization": f"Bearer {AMOCRM_TOKEN}",
                "Content-Type": "application/json"
            }
            response = requests.get(url, headers=headers)
            response.raise_for_status()  # Raise exception for HTTP errors

            data = response.json().get("_embedded", {}).get("elements", [])
            if not data:
                break

            elements.extend(data)
            page += 1

        except requests.RequestException as e:
            logging.error(f"❌ Failed to fetch catalog elements on page {page}: {str(e)}")
            break
        except Exception as e:
            logging.error(f"❌ Unexpected error while fetching catalog elements: {str(e)}")
            break

    return elements

def update_amo_prices_with_iiko():
    updated_items = []
    try:
        elements = fetch_catalog_elements()

        for element in elements:
            try:
                custom_fields = element.get("custom_fields_values", [])
                amo_price = None
                product_id = None
                size_id = None

                for field in custom_fields:
                    if field.get("field_id") == 419879:
                        amo_price = float(field["values"][0]["value"])
                    elif field.get("field_id") == 452745:
                        product_id = field["values"][0]["value"]
                    elif field.get("field_id") == 452747:
                        size_id = field["values"][0]["value"]

                if not product_id or amo_price is None:
                    continue

                iiko_item = get_menu_item(product_id, size_id)
                if not iiko_item:
                    logging.warning(f"⚠️ No matching iiko item for productId={product_id}, sizeId={size_id}")
                    continue

                iiko_price = float(iiko_item["price"])

                if iiko_price != amo_price:
                    logging.info(f"🔄 Updating price for {element['name']} from {amo_price} → {iiko_price}")
                    update_price_in_amocrm(element["id"], iiko_price)
                    updated_items.append({
                        "name": element["name"],
                        "old_price": amo_price,
                        "new_price": iiko_price
                    })

            except Exception as e:
                logging.error(f"❌ Error processing element {element.get('id')}: {str(e)}")

        return updated_items

    except Exception as e:
        logging.error(f"❌ Error updating AmoCRM prices: {str(e)}")
        return []

def update_price_in_amocrm(element_id: int, new_price: float):
    try:
        url = f"https://{AMOCRM_DOMAIN}/api/v4/catalogs/{AMOCRM_CATALOG_ID}/elements"
        headers = {
            "Authorization": f"Bearer {AMOCRM_TOKEN}",
            "Content-Type": "application/json"
        }

        payload = [{
            "id": element_id,
            "custom_fields_values": [
                {
                    "field_id": 419879,
                    "values": [{"value": new_price}]
                }
            ]
        }]

        response = requests.patch(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise exception for HTTP errors

        logging.info(f"✅ Price updated for element {element_id} → {new_price}")

    except requests.RequestException as e:
        logging.error(f"❌ Failed to update price for element {element_id}: {str(e)}")
    except Exception as e:
        logging.error(f"❌ Unexpected error while updating price for element {element_id}: {str(e)}")
