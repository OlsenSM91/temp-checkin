import os
import httpx
import base64
import urllib.parse
from pyconnectwise import ConnectWiseManageAPIClient

from dotenv import load_dotenv

load_dotenv()

# Load env
BASE_URL = os.getenv("CW_BASE_URL")
CLIENT_ID = os.getenv("CW_CLIENT_ID")
COMPANY_ID = os.getenv("CW_COMPANY_ID")
PUBLIC_API_KEY = os.getenv("CW_PUBLIC_API_KEY")
PRIVATE_API_KEY = os.getenv("CW_PRIVATE_API_KEY")

# Build headers
auth_string = f"{COMPANY_ID}+{PUBLIC_API_KEY}:{PRIVATE_API_KEY}"
encoded_auth_string = base64.b64encode(auth_string.encode()).decode()

HEADERS = {
    "Authorization": f"Basic {encoded_auth_string}",
    "clientId": CLIENT_ID,
    "Content-Type": "application/json",
    "Accept": "application/vnd.connectwise.com+json; version=3.0"
}

async def create_company_and_contact(
    name: str,
    address: str,
    address2: str,
    city: str,
    state: str,
    zip_code: str,
    company_phone: str,
    territory: str,
    first_name: str,
    last_name: str,
    email: str,
    phone: str
) -> tuple[str, str]:
    """Create a company and contact in ConnectWise using the format confirmed to work."""
    import httpx
    import re
    
    # Define the identifier generation function
    def generate_company_identifier(company_name: str, max_length=30):
        identifier = re.sub(r"[^a-zA-Z0-9]", "", company_name)[:max_length]
        return identifier or "TempCo"
    
    identifier = generate_company_identifier(name)
    print(f"[DEBUG] Creating company: {name} with identifier: {identifier}")
    
    try:
        # Create the company with the format that was confirmed to work
        company_data = {
            "identifier": identifier,
            "name": name,
            "addressLine1": address,
            "addressLine2": address2,
            "city": city,
            "state": state,
            "zip": zip_code,
            "phoneNumber": company_phone,
            "territory": {"name": territory},
            "site": {"name": "Main Office"},
            "types": [{"id": 1}]  # Client type - required!
        }
        
        print(f"[DEBUG] Company data: {company_data}")
        
        # Use the headers that worked in your test (without Accept header)
        headers = {
            "Authorization": f"Basic {encoded_auth_string}",
            "clientId": CLIENT_ID,
            "Content-Type": "application/json"
        }
        
        async with httpx.AsyncClient() as client:
            # Create the company
            company_resp = await client.post(
                f"{BASE_URL}/company/companies", 
                headers=headers, 
                json=company_data,
                timeout=30.0
            )
            
            print(f"[DEBUG] Company creation response: {company_resp.status_code} - {company_resp.text}")
            
            if company_resp.status_code != 201:
                raise Exception(f"Failed to create company: {company_resp.text}")
            
            created_company = company_resp.json()
            company_id = created_company['id']
            print(f"[DEBUG] Company created with ID: {company_id}")
            
            # Now create the contact using the same header format
            contact_data = {
                "firstName": first_name,
                "lastName": last_name,
                "company": {"id": company_id},
                "communicationItems": [
                    {
                        "type": {"id": 1},  # Email
                        "value": email,
                        "communicationType": "Email"
                    },
                    {
                        "type": {"id": 4},  # Mobile
                        "value": phone,
                        "communicationType": "Phone"
                    }
                ]
            }
            
            contact_resp = await client.post(
                f"{BASE_URL}/company/contacts", 
                headers=headers, 
                json=contact_data,
                timeout=30.0
            )
            
            print(f"[DEBUG] Contact creation response: {contact_resp.status_code} - {contact_resp.text}")
            
            if contact_resp.status_code != 201:
                raise Exception(f"Failed to create contact: {contact_resp.text}")
            
            created_contact = contact_resp.json()
            contact_id = created_contact['id']
            print(f"[DEBUG] Contact created with ID: {contact_id}")
            
            # Optional: Update the company with the default contact
            try:
                update_data = {
                    "id": company_id,
                    "defaultContact": {"id": contact_id}
                }
                
                update_resp = await client.patch(
                    f"{BASE_URL}/company/companies/{company_id}", 
                    headers=headers, 
                    json=update_data,
                    timeout=30.0
                )
                
                print(f"[DEBUG] Company update response: {update_resp.status_code} - {update_resp.text}")
            except Exception as update_error:
                print(f"[WARNING] Failed to update company with default contact: {str(update_error)}")
                # Continue without failing since we already have company and contact
            
            return str(company_id), str(contact_id)
            
    except Exception as e:
        print(f"[ERROR] Exception in create_company_and_contact: {str(e)}")
        raise Exception(f"Failed to create company and contact: {str(e)}")

async def find_contact_by_phone(phone: str) -> list[dict]:
    from pyconnectwise import ConnectWiseManageAPIClient
    import os

    print(f"[LOOKUP START] Searching for normalized phone: {phone}")
    normalized_phone = ''.join(filter(str.isdigit, phone))

    # Hardcoded base URL for pyConnectWise compatibility
    BASE_URL = "services.cns4u.com"

    # Load secrets from .env
    CLIENT_ID = os.getenv("CW_CLIENT_ID")
    PUBLIC_KEY = os.getenv("CW_PUBLIC_API_KEY")
    PRIVATE_KEY = os.getenv("CW_PRIVATE_API_KEY")
    COMPANY_ID = os.getenv("CW_COMPANY_ID")

    # Instantiate client using positional args
    client = ConnectWiseManageAPIClient(
        COMPANY_ID,
        BASE_URL,
        CLIENT_ID,
        PUBLIC_KEY,
        PRIVATE_KEY
    )

    # Perform the lookup using the conditions param
    contacts = client.company.contacts.get(params={
        "conditions": f'defaultPhoneNbr="{normalized_phone}"'
    })

    if not contacts:
        print("[LOOKUP COMPLETE] No contacts found.")
        return []

    enriched_contacts = []

    for contact in contacts:
        # Check for valid company ID
        if contact.company and contact.company.id:
            try:
                company = client.company.companies.id(contact.company.id).get()
                contact_data = contact.model_dump()
                contact_data["company"] = company.model_dump()
                enriched_contacts.append(contact_data)
            except Exception as e:
                print(f"[COMPANY LOOKUP FAILED] Contact {contact.id}: {e}")
        else:
            print(f"[WARNING] No company on contact {contact.id}")

    return enriched_contacts
