
import hmac
import hashlib
import json
import urllib.request
import urllib.error
import time

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

# Payload: PR Opened
pr_payload = {
    "action": "opened",
    "number": 1,
    "pull_request": {
        "number": 1,
        "title": "Fix memory leak in scanner",
        "body": "This PR fixes a critical memory leak issue.",
        "html_url": "http://182.96.17.140:82/owner/deep-audit-test/pulls/1",
        "head": {
            "ref": "feature/memory-fix",
            "sha": "a1b2c3d4e5f6g7h8i9j0"
        },
        "base": {
            "ref": "main"
        },
        "user": {
            "id": 999,
            "login": "developer"
        }
    },
    "repository": {
        "id": 123,
        "name": "deep-audit-test",
        "full_name": "owner/deep-audit-test",
        "owner": {
            "login": "owner",
            "email": "owner@example.com"
        },
        "html_url": "http://182.96.17.140:82/owner/deep-audit-test",
        "clone_url": "http://182.96.17.140:82/owner/deep-audit-test.git",
        "default_branch": "main",
        "description": "A test repository for DeepAudit CI"
    },
    "sender": {
        "login": "developer"
    }
}

if __name__ == "__main__":
    send_webhook("pull_request", pr_payload)
