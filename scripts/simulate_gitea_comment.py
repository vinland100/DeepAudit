
import hmac
import hashlib
import json
import urllib.request
import urllib.error

# Configuration
SECRET = "zheke@703"
URL = "http://127.0.0.1:8000/api/v1/webhooks/gitea"

def send_webhook(event_type, payload):
    payload_json = json.dumps(payload).encode('utf-8')
    signature = hmac.new(
        key=SECRET.encode(),
        msg=payload_json,
        digestmod=hashlib.sha256
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Gitea-Event": event_type,
        "X-Gitea-Signature": signature
    }

    req = urllib.request.Request(URL, data=payload_json, headers=headers, method='POST')

    try:
        print(f"Sending {event_type} to {URL}...")
        with urllib.request.urlopen(req) as response:
            print(f"Status: {response.status}")
            print(f"Response: {response.read().decode()}")
    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code}")
        print(f"Response: {e.read().decode()}")
    except Exception as e:
        print(f"Error: {e}")

# Payload from User
# Replaced localhost with 127.0.0.1 for safety if needed, but strings don't matter much for logic unless parsed.
payload = {
  "action": "created",
  "issue": {
    "id": 7,
    "number": 6,
    "title": "ai-bot-pr-test-4",
    "body": "ai-bot-pr-test-4",
    "state": "open",
    "pull_request": {
      "merged": False,
      "merged_at": None
    },
    "repository": {
      "id": 1,
      "name": "SpaceSim",
      "owner": "vinland100",
      "full_name": "vinland100/SpaceSim"
    },
  },
  "comment": {
    "id": 62,
    "body": "@ai-bot",
    "user": {
      "id": 1,
      "login": "vinland100"
    }
  },
  "repository": {
    "id": 1,
    "owner": {
      "id": 1,
      "login": "vinland100",
      "email": "wuyanbo5210@qq.com"
    },
    "name": "SpaceSim",
    "full_name": "vinland100/SpaceSim",
    "html_url": "http://localhost:3333/vinland100/SpaceSim",
    "clone_url": "http://localhost:3333/vinland100/SpaceSim.git",
    "default_branch": "main",
    "description": "SpaceSim"
  },
  "sender": {
    "id": 1,
    "login": "vinland100"
  },
  "is_pull": True
}

if __name__ == "__main__":
    send_webhook("issue_comment", payload)
