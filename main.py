import uvicorn
import requests
from requests.exceptions import RequestException, ConnectionError, Timeout 
from fastapi import FastAPI, Query, HTTPException, Header
from pydantic import BaseModel
from itsdangerous import URLSafeTimedSerializer, BadSignature
import time
import os
from dotenv import load_dotenv
app = FastAPI()
load_dotenv()
Secret_Key = os.getenv('SECRET_KEY')
API_Key = os.getenv('API_KEY')
serializer = URLSafeTimedSerializer(Secret_Key)
Base_URL = "https://stumble-financial-buckskin.ngrok-free.dev"
Webhook_URL_for_make_confirmation = os.getenv("WEBHOOK_CONFIRMATION_URL")
class LeaveLinkRequest(BaseModel):
    Request_ID : int
    Employee_ID : str
@app.post("/generate-links")
def generate_links(data: LeaveLinkRequest, x_api_key : str = Header(...)):
    if x_api_key != API_Key:
        raise HTTPException(status_code=401, detail="API key is Missing or wrong!")
    approved_payload = {"Request_ID" : data.Request_ID, "Employee_ID" : data.Employee_ID, "action" : "approved"}
    rejected_payload = {"Request_ID" : data.Request_ID, "Employee_ID" : data.Employee_ID, "action" : "rejected"}
    approved_token = serializer.dumps(approved_payload)
    rejected_token = serializer.dumps(rejected_payload)
    approval_link = f'{Base_URL}/leave/verify?token={approved_token}'
    rejection_link = f'{Base_URL}/leave/verify?token={rejected_token}'
    return {"approval_link" : approval_link, "rejection_link" : rejection_link}

max_retries = 3

@app.get('/leave/verify')
def webhook_confirmation(token: str = Query(...)):
    try:
        check = serializer.loads(token, max_age=86400)
        
        Request_ID = check["Request_ID"]
        Employee_ID = check["Employee_ID"]
        Approval_Status = check["action"]
        
        webhook_payload = {
            "Request_ID" : Request_ID,
            "Employee_ID" : Employee_ID, 
            "Approval_Status" : Approval_Status
        }
        
        response_success = False
        
        for attempts in range(max_retries):
            try:
                response = requests.post(url=Webhook_URL_for_make_confirmation, timeout=30, json=webhook_payload)
                response.raise_for_status()
                response_success = True
                break
            except ConnectionError as e:
                print(f"Connection error retrying... {e}")
                time.sleep(3)
            except Timeout as ee:
                print(f'Timeout Error. Making another attempt.. {ee}')
                time.sleep(3)
            except RequestException as em:
                print(f'Bad Request or Server Error: {em}')
                if em.response is not None and 400 <= em.response.status_code < 500:
                    print("Client Error 4xx. Breaking the loop")
                    break
                time.sleep(3) 
        
        if response_success:
            make_response = response.json()
            if make_response.get('Approval Status') ==  "Already processed":
                return {"status": "already_processed", "message": "The approval status has been already updated."}
            
            return { 
                "status": "success",
                "message": f"Leave request for Employee {Employee_ID} has been successfully {Approval_Status}."
            }
        else:
            raise HTTPException(status_code=502, detail="Unable to send the info to make.com")
            
    except BadSignature:
         raise HTTPException(status_code=400, detail="Token is invalid or expired.")
if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port = 8000, reload=True)        


