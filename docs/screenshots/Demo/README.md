## End-to-End Workflow Demo

This demo traces a single, unique leave request: a standard request under 5 days with no supporting document attached. As a result, the Google Drive download branch is expected to be skipped throughout the run.



![Step 1: Form Submission](/docs/screenshots/google-form-submission.png)


*Step 1: Form Submission*
> Employee submits the leave request through the Google Form, initiating the automation pipeline.



![Step 2: Response Logged in Google Sheets](/docs/screenshots/response-logged-in-google-sheets.png)


*Step 2: Response Logged in Google Sheets*
> The response appears in "Form responses 1", where a minimal Apps Script trigger fires the Make.com webhook.



![Step 3: Successful Scenario Execution](/docs/screenshots/main-trigger-scenario.png)


*Step 3: Successful Scenario Execution*
> The execution overview shows the successful run path; Drive-related modules appear skipped since no document was uploaded.



![Step 4: Gemini Output Parsed](/docs/screenshots/gemini-output-parsed.png)


*Step 4: Gemini Output Parsed*
> The Gemini response is parsed into structured fields, with summary and urgency as the key extracted values.



![Step 5: FastAPI Approval Links Generated](/docs/screenshots/fastapi-approval-link-generation.png)


*Step 5: FastAPI Approval Links Generated*
> The HTTP module receives a 200 OK response from the FastAPI backend containing signed approval and rejection links.



![Step 6: Manager Notification Sent](/docs/screenshots/manager's-inbox.png)


*Step 6: Manager Notification Sent*
> The manager receives an email containing the AI-generated summary, urgency level, and approval/rejection links.



![Step 7: Employee Notified of Pending Request](/docs/screenshots/employee-notified-of-pending.png)


*Step 7: Employee Notified of Pending Request*
> The employee receives confirmation that the request was received and is pending manager approval.



![Step 8: Manager Approves the Request](/docs/screenshots/json-response-from-backend.png)


*Step 8: Manager Approves the Request*
> The manager clicks the Approve link; the FastAPI backend returns a success JSON response confirming approval.



![Step 9: Status Updated in Google Sheets](/docs/screenshots/updated-status.png)


*Step 9: Status Updated in Google Sheets*
> The corresponding row in Google Sheets is updated to reflect the approved status.



![Step 10: Employee Receives Final Approval Email](/docs/screenshots/employee-recieives-final-confirmation.png)


*Step 10: Employee Receives Final Approval Email*
> The employee receives the final notification confirming the leave request has been approved.



![Step 11: Idempotency Verified on Repeated Click](/docs/screenshots/Idempotency-check.png)


*Step 11: Idempotency Verified on Repeated Click*
> The same approval link is clicked again; the backend returns `already_processed`, confirming idempotent behavior.
