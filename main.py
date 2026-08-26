import os
import time
import secrets
import requests
from dotenv import load_dotenv

import uvicorn
from fastapi import FastAPI, Query, Header, HTTPException, Depends
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
from requests.exceptions import RequestException, ConnectionError, Timeout
from itsdangerous import URLSafeTimedSerializer, BadSignature

# Load environment configuration
load_dotenv()
BASE_URL = os.getenv("BASE_URL")
WEBHOOK_CONFIRMATION_URL = os.getenv("WEBHOOK_CONFIRMATION_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
API_KEY = os.getenv("API_KEY")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "secret123")

app = FastAPI(title="Leave Management Backend & Admin Portal")

# 1. Mount static directory for frontend assets
app.mount("/static", StaticFiles(directory="static"), name="static")

Serializer = URLSafeTimedSerializer(SECRET_KEY)
security = HTTPBasic()


# --- Security Helpers ---
def verify_admin(credentials: HTTPBasicCredentials = Depends(security)):
    """Validates HTTP Basic Auth credentials for the /admin dashboard."""
    is_user_correct = secrets.compare_digest(credentials.username, ADMIN_USERNAME)
    is_pass_correct = secrets.compare_digest(credentials.password, ADMIN_PASSWORD)
    if not (is_user_correct and is_pass_correct):
        raise HTTPException(
            status_code=401,
            detail="Incorrect admin username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


# --- Request Schemas ---
class LeaveRequest(BaseModel):
    Request_ID: str
    Employee_ID: str

class SubmitActionRequest(BaseModel):
    token: str


# --- Routes ---

# 1. Generate Timed Links (called by automation pipeline)
@app.post("/generate-links")
def generate_links(data: LeaveRequest, x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    approval_payload = {
        "Employee_ID": data.Employee_ID, 
        "Request_ID": data.Request_ID, 
        "Approval_Status": "approved"
    }
    rejection_payload = {
        "Employee_ID": data.Employee_ID, 
        "Request_ID": data.Request_ID, 
        "Approval_Status": "rejected"
    }
    
    approved_token = Serializer.dumps(approval_payload)
    rejection_token = Serializer.dumps(rejection_payload)
    
    approval_link = f'{BASE_URL}/leave/portal?token={approved_token}'
    rejection_link = f'{BASE_URL}/leave/portal?token={rejection_token}'
    
    return {"approval_link": approval_link, "rejection_link": rejection_link}


# 2. Manager Leave Review Portal
@app.get("/leave/portal")
def leave_portal(token: str = Query(None)):
    """Serves the manager approval/rejection review interface."""
    return FileResponse("static/index.html")


# 3. Dynamic Data Fetching Endpoint (for pre-loading details before Confirm)
@app.get("/api/verify-token")
def verify_token_details(token: str = Query(...)):
    """Decrypts the token safely without executing the webhook and returns details for UI."""
    try:
        check = Serializer.loads(token, max_age=86400)
        return {
            "status": "success",
            "Employee_ID": check["Employee_ID"],
            "Request_ID": check["Request_ID"],
            "Action": check["Approval_Status"]
        }
    except BadSignature:
        raise HTTPException(status_code=400, detail="Token is expired or tampered. Please request a new one.")


# 4. Final Submission Endpoint (triggered when manager confirms action in portal)
max_retries = 3

@app.post("/api/submit-action")
def submit_action(payload: SubmitActionRequest):
    token = payload.token
    response = None
    response_success = False
    
    try:
        check = Serializer.loads(token, max_age=86400)
        webhook_payload = {
            "Request_ID": check["Request_ID"], 
            "Employee_ID": check["Employee_ID"], 
            "Approval_Status": check["Approval_Status"]
        }
        
        for attempts in range(max_retries):
            try:
                response = requests.post(url=WEBHOOK_CONFIRMATION_URL, timeout=30, json=webhook_payload)
                response.raise_for_status()
                response_success = True
                break
            except ConnectionError:
                print("Connection Failed. Making another attempt.")
                time.sleep(5)
            except Timeout:
                print("Connection Timeout. Making another attempt.")
                time.sleep(5)
            except RequestException as e:
                print(f"Bad request or server error: {e}")
                if e.response is not None and 400 <= e.response.status_code < 500:
                    print(f"Client Error {e}. Breaking the request.")
                    break
                    
        if response_success:
            make_response = response.json()
            if make_response.get("Approval_Status") == "Already processed":
                return {
                    "status": "already_processed", 
                    "message": "This link has already been used. The status is already updated."
                }
            else:
                return {
                    "status": "success",
                    "message": f"Leave request for Employee {check['Employee_ID']} has been successfully {check['Approval_Status']}."
                }
        else:
            raise HTTPException(status_code=502, detail="Internal Server Error")
            
    except BadSignature:
        raise HTTPException(status_code=400, detail="Token is expired or tampered. Please request a new one.")


# 5. Secure Admin Dashboard Endpoint
@app.get("/admin")
def admin_dashboard(username: str = Depends(verify_admin)):
    """Serves the Admin Dashboard UI protected via HTTP Basic Auth."""
    return FileResponse("static/admin_dashboard.html")


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
