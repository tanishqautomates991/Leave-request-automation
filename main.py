import os
import time
import secrets
import requests
from dotenv import load_dotenv
from typing import Optional

import uvicorn
from fastapi import FastAPI, Query, Header, HTTPException, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse
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

# Absolute path resolution (Ensures Render finds static files regardless of working directory)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
ADMIN_HTML_PATH = os.path.join(STATIC_DIR, "admin_dashboard.html")
INDEX_HTML_PATH = os.path.join(STATIC_DIR, "index.html")

app = FastAPI(title="Leave Management Backend & Admin Portal")

# Mount static directory for frontend assets
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

Serializer = URLSafeTimedSerializer(SECRET_KEY)
security = HTTPBasic(auto_error=False)


# --- Robust Authentication Helpers ---
def get_admin_credentials():
    """Fetches and sanitizes admin credentials from environment."""
    raw_user = os.getenv("ADMIN_USERNAME") or "admin"
    raw_pass = os.getenv("ADMIN_PASSWORD") or "secret123"
    # Strip whitespace, newlines, and accidental quotes (" or ') added in Render env UI
    clean_user = raw_user.strip().strip("\"'")
    clean_pass = raw_pass.strip().strip("\"'")
    return clean_user, clean_pass


def verify_admin_access(
    key: Optional[str] = Query(None),
    credentials: Optional[HTTPBasicCredentials] = Depends(security)
):
    """
    Dual-layer Admin Auth:
    1. Direct URL access: /admin?key=secret123
    2. HTTP Basic Auth: Browser prompt popup (admin / secret123)
    """
    expected_user, expected_pass = get_admin_credentials()

    # Option 1: URL Key Parameter check (e.g. /admin?key=secret123)
    if key:
        clean_key = key.strip().strip("\"'")
        if secrets.compare_digest(clean_key, expected_pass):
            print(f"[AUTH] Admin access granted via query key.")
            return expected_user

    # Option 2: HTTP Basic Auth check (Browser popup)
    if credentials:
        clean_user = (credentials.username or "").strip().strip("\"'")
        clean_pass = (credentials.password or "").strip().strip("\"'")
        
        is_user_correct = secrets.compare_digest(clean_user, expected_user)
        is_pass_correct = secrets.compare_digest(clean_pass, expected_pass)
        
        if is_user_correct and is_pass_correct:
            print(f"[AUTH] Admin access granted for user '{clean_user}'.")
            return clean_user
        else:
            print(f"[AUTH FAILED] Attempted User: '{clean_user}'. Expected User: '{expected_user}'. Check credentials in Render.")

    # If neither method is valid, trigger the browser Basic Auth login prompt with proper realm
    raise HTTPException(
        status_code=401,
        detail="Invalid credentials. Please enter valid admin username and password.",
        headers={"WWW-Authenticate": 'Basic realm="Leave Admin Portal"'},
    )


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
    if os.path.exists(INDEX_HTML_PATH):
        return FileResponse(INDEX_HTML_PATH)
    return HTMLResponse("<h2>Error: static/index.html not found on server.</h2>", status_code=404)


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
def admin_dashboard(username: str = Depends(verify_admin_access)):
    """Serves the Admin Dashboard UI protected via Basic Auth or Direct Key."""
    if os.path.exists(ADMIN_HTML_PATH):
        return FileResponse(ADMIN_HTML_PATH)
    return HTMLResponse("<h2>Error: static/admin_dashboard.html not found on server.</h2>", status_code=404)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
