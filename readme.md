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

```bash
gcloud services enable secretmanager.googleapis.com

echo -n "aws-1-ap-south-1.pooler.supabase.com" | gcloud secrets create DB_HOST --data-file=-
echo -n "5432" | gcloud secrets create DB_PORT --data-file=-
echo -n "postgres" | gcloud secrets create DB_NAME --data-file=-
echo -n "postgres.yourprojectref" | gcloud secrets create DB_USER --data-file=-
echo -n "YOUR_DB_PASSWORD" | gcloud secrets create DB_PASSWORD --data-file=-
echo -n "YOUR_VAPI_API_KEY" | gcloud secrets create VAPI_API_KEY --data-file=-
echo -n "https://your-host/api/calls/webhook/" | gcloud secrets create VAPI_WEBHOOK_URL --data-file=-
echo -n "YOUR_VAPI_WEBHOOK_SECRET" | gcloud secrets create VAPI_WEBHOOK_SECRET --data-file=-
echo -n "your-production-secret-key" | gcloud secrets create DJANGO_SECRET_KEY --data-file=-

gcloud projects describe boostedcalls --format="value(projectNumber)"
PROJECT_NUMBER=123456789012
SERVICE_ACCOUNT=${PROJECT_NUMBER}-compute@developer.gserviceaccount.com


```

### run this for each secret
```bash
gcloud secrets add-iam-policy-binding DB_HOST \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/secretmanager.secretAccessor"

```



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


Security notes
--------------
- Never commit `key.json` or other secrets into source control. Use Secret Manager (GCP) or GitHub Secrets for CI/CD.
- When deploying to Cloud Run, prefer referencing secrets from Secret Manager rather than placing them directly in the `--set-env-vars` deployment flag.
