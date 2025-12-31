
import requests
import json
import sys

# Configuration
GITEA_HOST = "http://182.96.17.140:82"
TOKEN = "8b0687d58aa70a09f5493737565b00f0b87eb868"
OWNER = "vinland100"
REPO = "SpaceSim"
PR_INDEX = "4"

# API Endpoint
# Note: Gitea PRs are issues, so we use the issues endpoint to comment
api_url = f"{GITEA_HOST}/api/v1/repos/{OWNER}/{REPO}/issues/{PR_INDEX}/comments"

headers = {
    "Authorization": f"token {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json"
}

data = {
    "body": "🤖 **DeepAudit Bot Test**: verifying access token permissions.\n\nRunning from test script."
}

def test_comment():
    print(f"Testing access to: {api_url}")
    print(f"Using Token: {TOKEN[:5]}...{TOKEN[-5:]}")
    
    try:
        response = requests.post(api_url, headers=headers, json=data, timeout=10)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 201:
            print("✅ Success! Comment posted.")
            print("Response:", json.dumps(response.json(), indent=2))
        else:
            print("❌ Failed.")
            print("Response:", response.text)
            
    except Exception as e:
        print(f"❌ Error occurred: {e}")

if __name__ == "__main__":
    test_comment()
