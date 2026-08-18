import requests
import json
import time

render_key = "rnd_x91LxViSJzNQvzuuBYTOEPbfXvBx"

headers = {
    "Authorization": f"Bearer {render_key}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

r_owner = requests.get("https://api.render.com/v1/owners", headers=headers)
owners = r_owner.json()
owner_id = owners[0]['owner']['id'] if owners else None

payload = {
    "type": "web_service",
    "name": "boca-raton-foia-bot",
    "ownerId": owner_id,
    "repo": "https://github.com/JorgeJoseContreras/boca-raton-foia-bot",
    "autoDeploy": "yes",
    "branch": "master",
    "serviceDetails": {
        "env": "python",
        "envSpecificDetails": {
            "buildCommand": "./build.sh",
            "startCommand": "gunicorn app:app"
        },
        "region": "oregon",
        "plan": "starter",
        "disk": {
            "name": "sqlite-data",
            "mountPath": "/data",
            "sizeGB": 1
        }
    },
    "envVars": [
        {"key": "SENDER_EMAIL", "value": "jorge.property.123@gmail.com"},
        {"key": "SENDER_PASSWORD", "value": "YOUR_16_CHAR_APP_PASSWORD"},
        {"key": "IMAP_SERVER", "value": "imap.gmail.com"},
        {"key": "SMTP_SERVER", "value": "smtp.gmail.com"},
        {"key": "NOTIFICATION_EMAIL", "value": "jorge.property.123@gmail.com"},
        {"key": "REQUESTOR_FIRST_NAME", "value": "Jorge"},
        {"key": "REQUESTOR_LAST_NAME", "value": "Contreras"},
        {"key": "REQUESTOR_PHONE", "value": "555-555-5555"},
        {"key": "REQUESTOR_ADDRESS", "value": "123 Main St"},
        {"key": "REQUESTOR_CITY", "value": "Miami"},
        {"key": "REQUESTOR_STATE", "value": "FL"},
        {"key": "REQUESTOR_ZIP", "value": "33101"},
        {"key": "DATABASE_PATH", "value": "/data/foia.db"}
    ]
}

print("Deploying boca-raton-foia-bot to Render...")
r_create = requests.post("https://api.render.com/v1/services", headers=headers, json=payload)

if r_create.status_code in [200, 201]:
    data = r_create.json()
    service_id = data.get("id", "")
    print(f"Success! Service created: {data.get('service', {}).get('url', '')}")
    print("Triggering initial deploy...")
    requests.post(f"https://api.render.com/v1/services/{service_id}/deploys", headers=headers)
else:
    print(f"Error: {r_create.status_code}")
    print(r_create.text)
