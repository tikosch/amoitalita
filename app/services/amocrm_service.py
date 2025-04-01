import requests
import logging
import time
from app.config import AMOCRM_DOMAIN, AMOCRM_TOKEN

def get_child_lead_id(lead_id: int):
    """
    Fetches the child lead ID from the latest note with note_type 'lead_auto_created'.
    
    Parameters:
    - lead_id (int): The ID of the parent lead.
    - max_retries (int): Maximum number of attempts to fetch the child lead ID.
    - wait_time (int): Time in seconds to wait between retries.
    
    Returns:
    - int: The ID of the latest child lead if found, otherwise None.
    """
    MAX_RETRIES = 5
    WAIT_TIME = 20

    try:
        for attempt in range(MAX_RETRIES):
            try:
                url = f"https://{AMOCRM_DOMAIN}/api/v4/leads/{lead_id}/notes"
                headers = {
                    "Authorization": f"Bearer {AMOCRM_TOKEN}",
                    "Content-Type": "application/json"
                }

                response = requests.get(url, headers=headers)
                response.raise_for_status()  # Raise an exception for HTTP errors

                notes = response.json().get("_embedded", {}).get("notes", [])
                latest_note = None

                for note in notes:
                    # Check for the note with note_type 'lead_auto_created'
                    if note.get("note_type") == "lead_auto_created":
                        # Compare timestamps to find the latest note
                        if not latest_note or note.get("created_at", 0) > latest_note.get("created_at", 0):
                            latest_note = note
                
                if latest_note:
                    params = latest_note.get("params", {})
                    child_lead_id = params.get("lead_id")
                    if child_lead_id:
                        logging.info(f"✅ Found latest child lead ID: {child_lead_id} from note ID: {latest_note.get('id')}")
                        return child_lead_id

                logging.warning(f"⚠️ Attempt {attempt+1}/{MAX_RETRIES}: No 'lead_auto_created' note found for lead {lead_id}.")
                time.sleep(WAIT_TIME)

            except requests.RequestException as e:
                logging.error(f"❌ Network error while fetching notes for lead {lead_id} (attempt {attempt+1}/{MAX_RETRIES}): {str(e)}")
                time.sleep(WAIT_TIME)
        
        logging.error(f"❌ Unable to find 'lead_auto_created' note after {MAX_RETRIES} attempts for lead {lead_id}.")
        return None

    except Exception as e:
        logging.error(f"❌ Unexpected error in get_child_lead_id: {str(e)}")
        return None

    except requests.RequestException as e:
        logging.error(f"❌ Network error while fetching notes for lead {lead_id}: {str(e)}")
        return None
    except Exception as e:
        logging.error(f"❌ Unexpected error in get_child_lead_id: {str(e)}")
        return None

def add_note_to_amocrm(lead_id: int, text: str, service: str = ""):
    """
    Sends a note to a specific lead in AmoCRM.
    
    Parameters:
    - lead_id (int): The ID of the lead to add the note to.
    - text (str): The text content of the note.
    - service (str, optional): The name of the service (e.g., "iiko"). 
      If empty, note_type will be "common".
    """
    url = f"https://{AMOCRM_DOMAIN}/api/v4/leads/{lead_id}/notes"
    headers = {
        "Authorization": f"Bearer {AMOCRM_TOKEN}",
        "Content-Type": "application/json"
    }

    # Determine note type and payload structure
    if service:
        note_type = "service_message"
        params = {
            "service": service,
            "text": text
        }
    else:
        note_type = "common"
        params = {
            "text": text
        }

    payload = [
        {
            "note_type": note_type,
            "params": params
        }
    ]

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()  # Raise an exception for HTTP errors
        logging.info(f"✅ Note added to lead {lead_id} with type '{note_type}' and text: {text}")
        return response.json()
    except requests.RequestException as e:
        logging.error(f"❌ Failed to add note to lead {lead_id}: {str(e)}")
        return None

def get_lead_data(lead_id: str):
    """
    Fetches lead data and attached catalog products via the /links endpoint.
    Uses custom fields "productId" and "sizeId" instead of external_uid.
    """
    try:
        base_url = f"https://{AMOCRM_DOMAIN}/api/v4"
        headers = {
            "Authorization": f"Bearer {AMOCRM_TOKEN}",
            "Content-Type": "application/json"
        }

        # Step 1: Fetch lead info
        lead_url = f"{base_url}/leads/{lead_id}"
        try:
            lead_response = requests.get(lead_url, headers=headers)
            lead_response.raise_for_status()
        except requests.RequestException as e:
            logging.error(f"❌ Failed to fetch lead: {str(e)}")
            add_note_to_amocrm(lead_id, f"Ошибка при получении данных сделки", "amoCRM")
            return None

        lead_data = lead_response.json()

        # Step 2: Fetch linked catalog items
        links_url = f"{base_url}/leads/{lead_id}/links"
        try:
            links_response = requests.get(links_url, headers=headers)
            links_response.raise_for_status()
        except requests.RequestException as e:
            logging.warning(f"⚠️ No linked products found: {str(e)}")
            add_note_to_amocrm(lead_id, f"Нет связанных товаров", "amoCRM")
            lead_data["_embedded"] = {"products": []}
            return lead_data

        linked_items = links_response.json().get("_embedded", {}).get("links", [])
        enriched_products = []

        for link in linked_items:
            if link.get("to_entity_type") != "catalog_elements":
                continue

            catalog_id = link["metadata"].get("catalog_id")
            element_id = link["to_entity_id"]
            quantity = link["metadata"].get("quantity", 1)

            # Fetch catalog element
            element_url = f"{base_url}/catalogs/{catalog_id}/elements/{element_id}"
            try:
                element_response = requests.get(element_url, headers=headers)
                element_response.raise_for_status()
            except requests.RequestException as e:
                logging.warning(f"⚠️ Could not fetch catalog element {element_id}: {str(e)}")
                add_note_to_amocrm(lead_id, f"Не удалось получить элемент каталога {element_id}", "amoCRM")
                continue

            element = element_response.json()
            custom_fields = element.get("custom_fields_values", [])
            product_id = None
            size_id = None

            for field in custom_fields:
                try:
                    if field.get("field_name") == "productId":
                        product_id = field["values"][0]["value"]
                    elif field.get("field_name") == "sizeId":
                        size_id = field["values"][0]["value"]
                except (IndexError, KeyError) as e:
                    logging.warning(f"⚠️ Error parsing field {field.get('field_name')}: {str(e)}")
                    add_note_to_amocrm(lead_id, f"Ошибка при разборе поля {field.get('field_name')}", "amoCRM")

            if not product_id:
                logging.warning(f"⚠️ Catalog element {element_id} has no productId, skipping")
                add_note_to_amocrm(lead_id, f"Элемент каталога {element_id} не имеет productId, пропущено", "amoCRM")
                continue

            enriched_products.append({
                "productId": product_id,
                "sizeId": size_id,
                "quantity": quantity
            })

        lead_data["_embedded"] = {"products": enriched_products}
        return lead_data

    except Exception as e:
        logging.error(f"❌ Unexpected error in get_lead_data: {str(e)}")
        add_note_to_amocrm(lead_id, f"Непредвиденная ошибка в получении данных сделки", "amoCRM")
        return None


def update_lead_status_in_amocrm(lead_id: int, status: int):
    """
    Update the lead's status to closed in AmoCRM.
    """
    try:
        url = f"https://{AMOCRM_DOMAIN}/api/v4/leads/{lead_id}"
        headers = {
            "Authorization": f"Bearer {AMOCRM_TOKEN}",
            "Content-Type": "application/json"
        }

        payload = {
            "status_id": status
        }

        try:
            response = requests.patch(url, headers=headers, json=payload)
            response.raise_for_status()
        except requests.RequestException as e:
            logging.error(f"❌ Failed to update lead {lead_id} status: {str(e)}")
            add_note_to_amocrm(lead_id, "Не удалось обновить статус сделки", "amoCRM")
            return False

        logging.info(f"✅ Lead {lead_id} status updated to Successful")
        add_note_to_amocrm(lead_id, "Статус сделки был изменен на Успешно реализовано", "amoCRM")
        return True

    except Exception as e:
        logging.error(f"❌ Unexpected error in update_lead_status_in_amocrm: {str(e)}")
        add_note_to_amocrm(lead_id, "Непредвиденная ошибка в обновлении статуса сделки", "amoCRM")
        return False
