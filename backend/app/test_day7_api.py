import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def test_api_stream_and_approval():
    print("==================================================================")
    print("STEP 1: Test Server Health Check")
    print("==================================================================")
    res = requests.get(f"{BASE_URL}/")
    print(f"Health Check Response: {res.json()}")

    print("\n==================================================================")
    print("STEP 2: POST Invoice text to SSE Stream Endpoint")
    print("==================================================================")
    
    invoice_payload = {
        "invoice_text": "INVOICE ID: INV-8822\nPO NUMBER: PO-1001\nVendor: Acme IT Solutions\nTotal Amount Billed: $1750.00\nDescription: Server setup and extended software licensing"
    }

    thread_id = None
    stream_response = requests.post(
        f"{BASE_URL}/api/audit/stream", 
        json=invoice_payload, 
        stream=True
    )

    for line in stream_response.iter_lines():
        if line:
            line_text = line.decode("utf-8")
            if line_text.startswith("data:"):
                data = json.loads(line_text.replace("data: ", ""))
                print(f"[SSE Stream Event] -> Type: {data.get('event')} | Log: {data.get('log', data.get('message', ''))}")
                if "thread_id" in data:
                    thread_id = data["thread_id"]

    print(f"\nCaptured Interrupted Session Thread ID: {thread_id}")

    print("\n==================================================================")
    print("STEP 3: POST Human Approval decision for pending thread")
    print("==================================================================")
    
    approval_payload = {
        "thread_id": thread_id,
        "approved": True,
        "notes": "Approved by Finance Director via API testing suite."
    }

    approval_res = requests.post(f"{BASE_URL}/api/audit/approve", json=approval_payload)
    print(f"Approval Result: {approval_res.json()}")

    print("\n==================================================================")
    print("STEP 4: GET Audit Logs from SQL Server Endpoint")
    print("==================================================================")
    logs_res = requests.get(f"{BASE_URL}/api/audit/logs")
    logs_data = logs_res.json()
    
    if logs_res.status_code == 200 and "count" in logs_data:
        print(f"Total Audit Logs in SQL Server: {logs_data['count']}")
        if logs_data['count'] > 0:
            latest_log = logs_data['data'][0]
            print(f"Latest Record: {latest_log}")
    else:
        print(f"API Error ({logs_res.status_code}): {logs_data}")

if __name__ == "__main__":
    test_api_stream_and_approval()