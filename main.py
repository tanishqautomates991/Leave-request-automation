import os
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Query, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
from requests.exceptions import RequestException, ConnectionError, Timeout
from itsdangerous import URLSafeTimedSerializer, BadSignature
import time

load_dotenv()
BASE_URL = os.getenv("BASE_URL")
WEBHOOK_CONFIRMATION_URL = os.getenv("WEBHOOK_CONFIRMATION_URL")
SECRET_KEY = os.getenv("SECRET_KEY")
API_KEY = os.getenv("API_KEY")

app = FastAPI()

# 1. Mount the static directory to serve HTML, CSS, JS files
app.mount("/static", StaticFiles(directory="static"), name="static")

Serializer = URLSafeTimedSerializer(SECRET_KEY)

class LeaveRequest(BaseModel):
    Request_ID: str
    Employee_ID: str

class SubmitActionRequest(BaseModel):
    token: str

@app.post("/generate-links")
def generate_links(data: LeaveRequest, x_api_key: str = Header(...)):
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    approval_payload = {"Employee_ID": data.Employee_ID, "Request_ID": data.Request_ID, "Approval_Status": "approved"}
    rejection_payload = {"Employee_ID": data.Employee_ID, "Request_ID": data.Request_ID, "Approval_Status": "rejected"}
    
    approved_token = Serializer.dumps(approval_payload)
    rejection_token = Serializer.dumps(rejection_payload)
    
    # Updated to point to the new portal endpoint instead of /leave/verify directly
    approval_link = f'{BASE_URL}/leave/portal?token={approved_token}'
    rejection_link = f'{BASE_URL}/leave/portal?token={rejection_token}'
    
    return {"approval_link": approval_link, "rejection_link": rejection_link}

# 2. Serve the frontend UI
@app.get("/leave/portal")
def leave_portal(token: str = Query(None)):
    """Serves the frontend interface where the manager will review the request."""
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

max_retries = 3

# 4. Final Submission Endpoint (triggered when "Confirm" is clicked in UI)
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
                return {"status": "already_processed", "message": "This link has already been used. The status is already updated."}
            else:
                return {
                    "status": "success",
                    "message": f"Leave request for Employee {check['Employee_ID']} has been successfully {check['Approval_Status']}."
                }
        else:
            raise HTTPException(status_code=502, detail="Internal Server Error")
            
    except BadSignature:
        raise HTTPException(status_code=400, detail="Token is expired or tampered. Please request a new one.")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
