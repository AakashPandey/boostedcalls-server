BoostedCalls
-------------
BoostedCalls is a Django 5.x backend that integrates with a Voice AI Provider (Vapi) to create, manage and analyze outbound calls. It exposes a REST API (Django REST Framework) for calls, contacts, and call scripts, receives webhooks from Vapi to keep call state in sync, and supports background sync of stale queued calls.

Prerequisites
-------------
- Python 3.11+ (for local development) or Docker for container runs
- PostgreSQL (or hosted Postgres)
- gcloud SDK (for Google Cloud deployment)

Local development
-----------------
1. Create & activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure environment variables (example):

```bash
export DB_HOST=localhost
export DB_PORT=5432
export DB_NAME=postgres
export DB_USER=postgres
export DB_PASSWORD="your-db-password"
export VAPI_API_KEY="<your-vapi-key>"
export VAPI_WEBHOOK_URL="https://your-host/api/calls/webhook/"
export VAPI_WEBHOOK_SECRET="<your-webhook-secret>"
```

4. Run migrations and optional initial sync:

```bash
python manage.py makemigrations
python manage.py migrate
python manage.py sync_stale_calls   # optional: reconciles queued calls
```

5. Run the development server:

```bash
python manage.py runserver
```

Docker (build & run)
--------------------
Build the image locally:

```bash
docker build -t boostedcalls .
```

Run the container (example):

```bash
docker run -e PORT=8080 -e DB_HOST=<db-host> -e DB_USER=<db-user> \
  -e DB_PASSWORD=<db-pass> -e DB_NAME=<db-name> -p 8080:8080 boostedcalls
```

If using Cloud SQL / managed Postgres, set the appropriate `DB_*` env vars or use a connector.

Google Cloud Run deployment
---------------------------
High-level steps to publish the Docker image to Artifact Registry and deploy to Cloud Run.

1. Enable required APIs:

```bash
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com secretmanager.googleapis.com
```

2. Create a service account for CI/CD (one-time):

```bash
gcloud iam service-accounts create github-deployer --display-name=github-deployer
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
gcloud iam service-accounts keys create key.json \
  --iam-account github-deployer@$PROJECT_ID.iam.gserviceaccount.com
```

3. Create an Artifact Registry repository (example region `asia-south1`):

```bash
gcloud artifacts repositories create django-repo --repository-format=docker --location=asia-south1
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-deployer@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"
```

4. Build & push an image to Artifact Registry:

```bash
gcloud auth configure-docker asia-south1-docker.pkg.dev
docker build -t asia-south1-docker.pkg.dev/$PROJECT_ID/django-repo/boostedcalls:latest .
docker push asia-south1-docker.pkg.dev/$PROJECT_ID/django-repo/boostedcalls:latest
```

5. Deploy to Cloud Run:

```bash
gcloud run deploy boostedcalls \
  --image asia-south1-docker.pkg.dev/$PROJECT_ID/django-repo/boostedcalls:latest \
  --region asia-south1 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars DB_HOST=$DB_HOST,DB_NAME=$DB_NAME,DB_USER=$DB_USER,DB_PASSWORD=$DB_PASSWORD,\
    VAPI_API_KEY=$VAPI_API_KEY,VAPI_WEBHOOK_SECRET=$VAPI_WEBHOOK_SECRET
```

Production notes
----------------
- Store secrets in Secret Manager and reference them in Cloud Run instead of embedding as plain env vars.


Useful commands
---------------
- Run migrations locally:

```bash
python manage.py migrate
```

- Reconcile stale queued calls (management command):

```bash
python manage.py sync_stale_calls
```

Additional setup notes
----------------------

Supabase (Postgres) setup
-------------------------
- Create a Supabase project at https://supabase.com and note the DB connection details (host, port, database name, user, password).
- In the Supabase project settings copy the connection string and use those values for the `DB_*` environment variables described above.

Vapi account (telephony) setup
-------------------------------
- Create an account at https://dashboard.vapi.ai/ and obtain an API key. This value should be stored in `VAPI_API_KEY`.
- Configure your webhook URL in the Vapi organization settings: https://dashboard.vapi.ai/settings/organization. Use the public URL that points to `/api/calls/webhook/` and set the webhook secret value which you will store in `VAPI_WEBHOOK_SECRET`.

Expose your local webhook with ngrok
----------------------------------
- Install and login to ngrok (macOS instructions): https://dashboard.ngrok.com/get-started/setup/macos
- Expose your local server (example):

```bash
ngrok http 8000
```

- Take the `https://*.ngrok.io` URL and set your Vapi webhook to `https://<your-ngrok-host>/api/calls/webhook/` and set the `VAPI_WEBHOOK_SECRET` to the same secret you configure in your environment.

Integrating webhook in Vapi
---------------------------
- In the Vapi dashboard (Organization settings) provide the public webhook URL and the secret. Vapi will send an `x-vapi-secret` header which the server validates.

Example GitHub repository secrets
---------------------------------
Add these secrets to your GitHub repo (Settings → Secrets) so CI/CD can deploy the service.

| Secret | Value |
|--------|-------|
| GCP_PROJECT_ID | your project id |
| GCP_SA_KEY | full contents of key.json (JSON string) |
| DB_HOST | aws-1-ap-south-1.pooler.supabase.com |
| DB_PORT | 5432 |
| DB_NAME | postgres |
| DB_USER | postgres.yourprojectref |
| DB_PASSWORD | your password |
| VAPI_API_KEY | vapi API key value |
| VAPI_WEBHOOK_URL | https://your-host/api/calls/webhook/ |
| VAPI_WEBHOOK_SECRET | webhook secret value |

Security notes
--------------
- Never commit `key.json` or other secrets into source control. Use Secret Manager (GCP) or GitHub Secrets for CI/CD.
- When deploying to Cloud Run, prefer referencing secrets from Secret Manager rather than placing them directly in the `--set-env-vars` deployment flag.

API endpoints reference
----------------------
All endpoints require JWT authentication (except /token/ and webhook) with the `Authorization: Bearer <token>` header.

Authentication
~~~~~~~~~~~~~~

POST /api/token/
  Get access token (required for all authenticated endpoints).
  Payload:
    {
      "username": "user@example.com",
      "password": "your-password"
    }
  Response (200):
    {
      "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
      "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
    }

POST /api/token/refresh/
  Refresh an expired access token.
  Payload:
    {
      "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
    }
  Response (200):
    {
      "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
    }

Calls
~~~~~

GET /api/calls/
  List all calls for the authenticated user (paginated).
  Query params: page=1, limit=20
  Response (200):
    {
      "total": 1284,
      "page": 1,
      "limit": 20,
      "data": [
        {
          "id": "uuid-here",
          "contact": {"id": "uuid", "name": "John Doe", "phone": "+1234567890"},
          "status": "completed",
          "transcript": "...",
          "summary": "...",
          "started_at": "2026-02-11T03:00:00Z",
          "ended_at": "2026-02-11T03:05:00Z",
          "duration_seconds": 300,
          "created_at": "2026-02-11T02:59:00Z"
        }
      ]
    }

POST /api/calls/
  Create a new outbound call.
  Payload:
    {
      "contact_id": "uuid-here",
      "assistant_id": "vapi-assistant-id",
      "phone_number_id": "vapi-phone-number-id",
      "script_id": "uuid-or-null",
      "custom_prompt": "optional custom prompt",
      "first_message": "optional first message",
      "call_goals": ["goal1", "goal2"],
      "metadata": {"key": "value"}
    }
  Response (201):
    {
      "id": "uuid-here",
      "status": "pending",
      "vapi_call_id": "vapi-call-id",
      "created_at": "2026-02-11T04:00:00Z"
    }

GET /api/calls/<call_id>/
  Get a single call (auto-syncs with Vapi if status is active).
  Response (200):
    {
      "id": "uuid-here",
      "contact": {...},
      "status": "completed",
      "transcript": "...",
      "summary": "...",
      "analysis": {...},
      "metadata": {"recordingUrl": "...", "cost": 0.50}
    }

POST /api/calls/<call_id>/cancel/
  Cancel a pending or active call.
  Response (200):
    {
      "id": "uuid-here",
      "status": "cancelled"
    }

POST /api/calls/<call_id>/sync/
  Manually sync call status with Vapi.
  Response (200):
    {
      "id": "uuid-here",
      "status": "completed"
    }

GET /api/calls/pending-count/
  Get count of active (non-terminal) calls for the user.
  Response (200):
    {
      "count": 5
    }

GET /api/calls/stats/
  Get dashboard statistics (cards and line chart).
  Response (200):
    {
      "cards": [
        {"title": "Total Spent on Calls", "value": "$50.00"},
        {"title": "Calls made", "value": "1284"},
        {"title": "Failed calls", "value": "38"},
        {"title": "Contacts", "value": "4902"}
      ],
      "lineChart": {
        "title": "Successful calls",
        "subtitle": "+18% vs previous 14 days",
        "badge": "Last 14 days",
        "points": [
          {"x": 0, "y": 118, "label": "Mon"},
          {"x": 1, "y": 102, "label": "Tue"}
        ]
      }
    }

POST /api/calls/webhook/ (no auth required)
  Vapi webhook endpoint. Receives call events.
  Header: x-vapi-secret: <webhook-secret>

Contacts
~~~~~~~~

GET /api/contacts/
  List all contacts for the authenticated user.
  Response (200):
    [
      {
        "id": "uuid-here",
        "name": "John Doe",
        "phone": "+1234567890",
        "email": "john@example.com",
        "metadata": {"key": "value"},
        "created_at": "2026-02-11T00:00:00Z"
      }
    ]

POST /api/contacts/
  Create a new contact.
  Payload:
    {
      "name": "Jane Doe",
      "phone": "+1987654321",
      "email": "jane@example.com",
      "metadata": {"key": "value"}
    }
  Response (201):
    {
      "id": "uuid-here",
      "name": "Jane Doe",
      "phone": "+1987654321",
      "email": "jane@example.com"
    }

GET /api/contacts/<contact_id>/
  Get a single contact.
  Response (200):
    {
      "id": "uuid-here",
      "name": "Jane Doe",
      "phone": "+1987654321"
    }

PUT /api/contacts/<contact_id>/
  Full update (replace) a contact.
  Payload:
    {
      "name": "Jane Updated",
      "phone": "+1987654321",
      "email": "jane.updated@example.com"
    }
  Response (200):
    {
      "id": "uuid-here",
      "name": "Jane Updated"
    }

PATCH /api/contacts/<contact_id>/
  Partial update a contact.
  Payload:
    {
      "email": "newemail@example.com"
    }
  Response (200):
    {
      "id": "uuid-here",
      "email": "newemail@example.com"
    }

DELETE /api/contacts/<contact_id>/
  Delete a contact.
  Response (200):
    {
      "message": "Contact deleted successfully."
    }

Call Scripts
~~~~~~~~~~~~

GET /api/scripts/
  List all call scripts for the authenticated user.
  Response (200):
    [
      {
        "id": "uuid-here",
        "name": "Sales Pitch",
        "description": "Standard sales call",
        "custom_prompt": "You are a sales rep...",
        "first_message": "Hi, this is...",
        "call_goals": ["Qualify lead", "Schedule demo"],
        "created_at": "2026-02-11T00:00:00Z"
      }
    ]

POST /api/scripts/
  Create a new call script.
  Payload:
    {
      "name": "Support Script",
      "description": "Technical support call",
      "custom_prompt": "You are a support agent...",
      "first_message": "Hi, how can I help?",
      "call_goals": ["Resolve issue", "Collect feedback"]
    }
  Response (201):
    {
      "id": "uuid-here",
      "name": "Support Script"
    }

GET /api/scripts/<script_id>/
  Get a single call script.
  Response (200):
    {
      "id": "uuid-here",
      "name": "Support Script",
      "description": "Technical support call"
    }

PUT /api/scripts/<script_id>/
  Full update a call script.
  Payload:
    {
      "name": "Updated Support Script",
      "description": "Updated description"
    }
  Response (200):
    {
      "id": "uuid-here",
      "name": "Updated Support Script"
    }

PATCH /api/scripts/<script_id>/
  Partial update a call script.
  Payload:
    {
      "description": "New description"
    }
  Response (200):
    {
      "id": "uuid-here",
      "description": "New description"
    }

DELETE /api/scripts/<script_id>/
  Delete a call script.
  Response (200):
    {
      "success": true
    }

Testing with curl
~~~~~~~~~~~~~~~~~
Get token:
```bash
curl -X POST http://localhost:8000/api/token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"user@example.com","password":"password"}'
```

List calls (using token):
```bash
curl -X GET http://localhost:8000/api/calls/ \
  -H "Authorization: Bearer <access_token>"
```

Create a contact:
```bash
curl -X POST http://localhost:8000/api/contacts/ \
  -H "Authorization: Bearer <access_token>" \
  -H "Content-Type: application/json" \
  -d '{"name":"John Doe","phone":"+1234567890","email":"john@example.com"}'
```


