from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.services import connectwise
from os import getenv
import httpx
import base64
from dotenv import load_dotenv

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

@router.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("home.html", {"request": request})

@router.get("/new", response_class=HTMLResponse)
async def new_client_form(request: Request):
    return templates.TemplateResponse("new_client.html", {
        "request": request,
        "google_maps_api_key": getenv("GOOGLE_MAPS_API_KEY")
    })

@router.post("/new")
async def handle_new_client(
    request: Request,
    business: str = Form(""),
    first_name: str = Form(...),
    last_name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    address: str = Form(...),
    address2: str = Form(""),
    city: str = Form(...),
    state: str = Form(...),
    zip: str = Form(...)
):
    company_name = business.strip() if business.strip() else f"{first_name} {last_name}"

    company_id, contact_id = await connectwise.create_company_and_contact(
        name=company_name,
        address=address,
        address2=address2,
        city=city,
        state=state,
        zip_code=zip,
        company_phone=phone,
        territory="Hollister",
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone
    )

    request.session["client"] = {
        "company_id": company_id,
        "contact_id": contact_id,
        "name": f"{first_name} {last_name}",
        "phone": phone,
        "email": email,
        "address": f"{address} {address2}, {city}, {state} {zip}".strip()
    }

    return RedirectResponse(url="/confirm", status_code=303)

@router.get("/returning", response_class=HTMLResponse)
async def returning_client_form(request: Request):
    return templates.TemplateResponse("returning_client.html", {"request": request})

@router.post("/returning", response_class=HTMLResponse)
async def handle_returning_client(request: Request, phone: str = Form(...)):
    from app.services.connectwise import find_contact_by_phone

    phone = ''.join(filter(str.isdigit, phone))
    # Store the phone number in session for potential future use
    request.session["last_phone_search"] = phone
    
    contacts = await find_contact_by_phone(phone)
    print("[DEBUG] Contacts found:", contacts)

    if not contacts:
        return templates.TemplateResponse("returning_client.html", {
            "request": request,
            "error": "No matching client found."
        })

    if len(contacts) == 1:
        # Use the data directly from the search results
        contact = contacts[0]
        
        # Extract email from communication_items
        email = ""
        for comm in contact.get("communication_items", []):
            if comm.get("communication_type") == "Email":
                email = comm.get("value", "")
                break
        
        # Set session data with snake_case keys from PyConnectWise
        request.session["client"] = {
            "company_id": contact["company"]["id"],
            "contact_id": contact["id"],
            "name": f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip(),
            "phone": contact.get("default_phone_nbr", ""),
            "email": email,
            "address": f"{contact['company'].get('address_line1', '')}, {contact['company'].get('city', '')}, {contact['company'].get('state', '')} {contact['company'].get('zip', '')}"
        }
        
        print("[DEBUG] Session set in single contact case:", request.session.get("client"))
        return RedirectResponse(url="/confirm", status_code=303)

    # For multiple contacts, pass them to the template
    return templates.TemplateResponse("select_contact.html", {
        "request": request,
        "contacts": contacts
    })

@router.post("/select-contact")
async def finalize_contact_selection(request: Request):
    # Debug the incoming form data
    form_data = await request.form()
    print("[DEBUG] Form data received:", dict(form_data))
    
    contact_id = form_data.get("contact_id")
    company_id = form_data.get("company_id")
    
    print("[DEBUG] Selected contact_id:", contact_id)
    print("[DEBUG] Selected company_id:", company_id)
    
    if not contact_id or not company_id:
        print("[ERROR] Missing contact_id or company_id")
        return templates.TemplateResponse("returning_client.html", {
            "request": request,
            "error": "Please select a contact to continue."
        })

    # Get the stored contacts from the phone search
    phone = request.session.get("last_phone_search", "")
    if not phone:
        # If no stored phone search, let's attempt to re-search
        # Should never happen in normal flow but good safety
        return RedirectResponse(url="/returning", status_code=303)
    
    from app.services.connectwise import find_contact_by_phone
    contacts = await find_contact_by_phone(phone)
    
    # Find the selected contact in the results
    selected_contact = None
    for contact in contacts:
        if str(contact["id"]) == contact_id:
            selected_contact = contact
            break
    
    if not selected_contact:
        print("[ERROR] Selected contact not found in results")
        return templates.TemplateResponse("returning_client.html", {
            "request": request,
            "error": "Selected contact not found. Please try again."
        })
    
    # Extract email from communication_items
    email = ""
    for comm in selected_contact.get("communication_items", []):
        if comm.get("communication_type") == "Email":
            email = comm.get("value", "")
            break
    
    # Set session data with the snake_case keys from PyConnectWise
    request.session["client"] = {
        "company_id": selected_contact["company"]["id"],
        "contact_id": selected_contact["id"],
        "name": f"{selected_contact.get('first_name', '')} {selected_contact.get('last_name', '')}".strip(),
        "phone": selected_contact.get("default_phone_nbr", ""),
        "email": email,
        "address": f"{selected_contact['company'].get('address_line1', '')}, {selected_contact['company'].get('city', '')}, {selected_contact['company'].get('state', '')} {selected_contact['company'].get('zip', '')}"
    }
    
    print("[DEBUG] Session set in multi-contact case:", request.session.get("client"))
    return RedirectResponse(url="/confirm", status_code=303)

@router.get("/confirm", response_class=HTMLResponse)
async def confirm_client_details(request: Request):
    print("[DEBUG] /confirm session contents:", request.session.get("client"))
    client = request.session.get("client")
    if not client:
        print("[DEBUG] No client found in session. Redirecting...")
        return RedirectResponse(url="/returning", status_code=302)

    return templates.TemplateResponse("confirm.html", {
        "request": request,
        "client": client
    })

@router.get("/issue", response_class=HTMLResponse)
async def issue_form(request: Request):
    client = request.session.get("client")
    if not client:
        return RedirectResponse("/", status_code=302)
    return templates.TemplateResponse("issue.html", {"request": request, "client": client})

@router.post("/issue")
async def handle_issue_submission(request: Request, description: str = Form(...)):
    from openai import AsyncOpenAI
    import json

    client_data = request.session.get("client")
    if not client_data:
        return RedirectResponse("/", status_code=302)

    openai_client = AsyncOpenAI(api_key=getenv("OPENAI_API_KEY"))

    prompt = f"""
You are a helpful IT support agent. A client submitted the following issue:

"{description}"

Please provide 2–3 clarifying questions that would help our techs resolve the issue faster. 
Always include a question about whether there is a login username/password for the affected system.
Respond only with the questions in numbered format.
"""

    completion = await openai_client.chat.completions.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=300
    )
    questions = completion.choices[0].message.content

    request.session["issue"] = {
        "initial": description,
        "followups": questions
    }

    return templates.TemplateResponse("followup.html", {
        "request": request,
        "questions": questions.splitlines(),
        "client": client_data
    })

@router.post("/create-ticket")
async def create_ticket(request: Request):
    form = await request.form()
    client = request.session.get("client")
    issue = request.session.get("issue")

    if not client or not issue:
        return RedirectResponse("/", status_code=302)

    # Match questions to responses
    questions = issue["followups"].splitlines()
    responses = [form.get(f"response_{i+1}", "") for i in range(len(questions))]

    followup_qna = "\n".join(
        f"{questions[i]}\nA: {responses[i]}" for i in range(len(questions))
    )

    full_description = f"""
Client Description:
{issue['initial']}

Follow-Up Responses:
{followup_qna}
"""

    from app.services.connectwise import BASE_URL, COMPANY_ID, PUBLIC_API_KEY, PRIVATE_API_KEY, CLIENT_ID

    auth_string = f"{COMPANY_ID}+{PUBLIC_API_KEY}:{PRIVATE_API_KEY}"
    encoded_auth_string = base64.b64encode(auth_string.encode()).decode()

    headers = {
        "Authorization": f"Basic {encoded_auth_string}",
        "clientId": CLIENT_ID,
        "Content-Type": "application/json"
    }

    ticket_data = {
        "company": {"id": client["company_id"]},
        "contact": {"id": client["contact_id"]},
        "summary": issue["initial"][:100],
        "initialDescription": full_description,
        "board": {"name": "RX Professional Services"},
        "status": {"name": "New (portal)"}
    }

    print("[DEBUG] Final ticket_data:", ticket_data)

    async with httpx.AsyncClient() as client_session:
        resp = await client_session.post(
            f"{BASE_URL}/service/tickets",
            headers=headers,
            json=ticket_data
        )

        if resp.status_code != 201:
            print("[TICKET ERROR]", resp.status_code)
            try:
                error_json = await resp.json()
                print("[TICKET ERROR MESSAGE]:", error_json.get("message", "No message"))
                if "errors" in error_json:
                    for err in error_json["errors"]:
                        print("[TICKET ERROR DETAIL]:", err.get("message", ""))
            except Exception as e:
                raw = await resp.aread()
                print("[TICKET ERROR RAW TEXT]:", raw.decode(errors="ignore"))
                print("[ERROR] Failed to parse ConnectWise error response:", e)

            raise Exception("Ticket creation failed.")

        ticket = resp.json()
        request.session["ticket_id"] = ticket["id"]

    return RedirectResponse(url="/payment", status_code=303)

@router.get("/payment", response_class=HTMLResponse)
async def collect_payment(request: Request):
    client = request.session.get("client")
    ticket_id = request.session.get("ticket_id")

    if not client or not ticket_id:
        return RedirectResponse("/", status_code=302)

    return templates.TemplateResponse("payment.html", {
        "request": request,
        "client": client,
        "ticket_id": ticket_id,
        "total_amount": 103.00,
        "deposit_amount": 100.00,
        "processing_fee": 3.00
    })

@router.post("/complete")
async def complete_checkin(request: Request):
    request.session.clear()

    return templates.TemplateResponse("complete.html", {
        "request": request
    })
