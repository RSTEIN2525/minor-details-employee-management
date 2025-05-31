# Production Deployment Guide

## Secure Authentication Setup (No Key Files in Code)

This guide shows how to set up Firebase authentication securely for different environments without committing service account keys to version control.

## 🔧 Environment Setup Options

### Option 1: Environment Variables (Recommended)

#### Step 1: Get Your Service Account Key
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Navigate to "IAM & Admin" > "Service Accounts"
3. Click "**Create Service Account**".
4. Give it a descriptive name (e.g., `employee-management-app-sa`) and an optional description.
5. **Grant necessary roles:**
   - `Firebase Admin SDK Administrator Service Agent` (provides broad Firebase admin capabilities)
   - `Storage Object Admin` (allows managing objects in your Firebase Storage bucket)
   *Alternatively, for more fine-grained control, you can create custom roles with only the specific permissions needed.*
6. Click "Continue". You can skip granting users access to this service account for now.
7. Click "Done".
8. Find your newly created service account in the list.
9. Click "Actions" (three dots) next to it > "Manage keys" > "Add Key" > "Create new key" > "JSON".
10. Download the JSON file. **Keep this file extremely secure and never commit it to version control!**

#### Step 2: Set Environment Variables

**For Local Development:**
```bash
# Option A: Create a .env file (add to .gitignore!)
echo "FIREBASE_SERVICE_ACCOUNT_KEY='$(cat path/to/your/serviceAccountKey.json)'" > .env
echo "FIREBASE_STORAGE_BUCKET=minordetails-1aff3.appspot.com" >> .env

# Option B: Export directly in your shell
export FIREBASE_SERVICE_ACCOUNT_KEY='{"type":"service_account","project_id":"your-project",...}'
export FIREBASE_STORAGE_BUCKET="minordetails-1aff3.appspot.com"
```

**For Production (various platforms):**

**Railway:**
```bash
railway variables set FIREBASE_SERVICE_ACCOUNT_KEY='{"type":"service_account",...}'
railway variables set FIREBASE_STORAGE_BUCKET="minordetails-1aff3.appspot.com"
```

**Heroku:**
```bash
heroku config:set FIREBASE_SERVICE_ACCOUNT_KEY='{"type":"service_account",...}'
heroku config:set FIREBASE_STORAGE_BUCKET="minordetails-1aff3.appspot.com"
```

**Docker:**
```dockerfile
# In Dockerfile or docker-compose.yml
ENV FIREBASE_SERVICE_ACCOUNT_KEY='{"type":"service_account",...}'
ENV FIREBASE_STORAGE_BUCKET="minordetails-1aff3.appspot.com"
```

**Google Cloud Run:**
```bash
gcloud run deploy your-app \
  --set-env-vars FIREBASE_SERVICE_ACCOUNT_KEY='{"type":"service_account",...}' \
  --set-env-vars FIREBASE_STORAGE_BUCKET="minordetails-1aff3.appspot.com"
```

### Option 2: Cloud-Native IAM (Google Cloud Only)

If deploying to Google Cloud Platform, you can use Workload Identity:

```bash
# Enable Workload Identity
gcloud container clusters update CLUSTER_NAME \
    --workload-pool=PROJECT_ID.svc.id.goog

# Create Kubernetes Service Account
kubectl create serviceaccount KSA_NAME

# Bind to Google Service Account
gcloud iam service-accounts add-iam-policy-binding \
    --role roles/iam.workloadIdentityUser \
    --member "serviceAccount:PROJECT_ID.svc.id.goog[NAMESPACE/KSA_NAME]" \
    GSA_NAME@PROJECT_ID.iam.gserviceaccount.com

# Annotate Kubernetes Service Account
kubectl annotate serviceaccount KSA_NAME \
    iam.gke.io/gcp-service-account=GSA_NAME@PROJECT_ID.iam.gserviceaccount.com
```

### Option 3: File Path (Local Development Only)

For local development, you can use a file path:

```bash
# Set path to your key file (outside of your project directory)
export FIREBASE_SERVICE_ACCOUNT_KEY_PATH="/secure/path/to/serviceAccountKey.json"
```

## 🔄 Code Changes Made

The backend now supports multiple authentication methods in this priority order:

1. **`FIREBASE_SERVICE_ACCOUNT_KEY`** environment variable (JSON string)
2. **`FIREBASE_SERVICE_ACCOUNT_KEY_PATH`** environment variable (file path)
3. **`GOOGLE_APPLICATION_CREDENTIALS`** environment variable (Google Cloud standard)
4. **Default Application Default Credentials** (fallback)

## 🚀 Deployment Instructions

### 1. Environment Variables Method (Recommended)

**Step 1:** Set up your environment variables in your deployment platform
**Step 2:** Deploy your application
**Step 3:** Verify initialization logs show: `"Firebase Admin SDK initialized with Service Account Key from environment variable."`

### 2. Google Cloud Deployment

**For Google Cloud Run:**
```bash
# Build and deploy
gcloud builds submit --tag gcr.io/PROJECT_ID/your-app
gcloud run deploy your-app \
  --image gcr.io/PROJECT_ID/your-app \
  --platform managed \
  --region us-central1 \
  --set-env-vars FIREBASE_SERVICE_ACCOUNT_KEY='{"type":"service_account",...}' \
  --set-env-vars FIREBASE_STORAGE_BUCKET="minordetails-1aff3.appspot.com"
```

**For Google Kubernetes Engine:**
```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: your-app
spec:
  template:
    spec:
      serviceAccountName: your-ksa  # With Workload Identity
      containers:
      - name: your-app
        image: gcr.io/PROJECT_ID/your-app
        env:
        - name: FIREBASE_STORAGE_BUCKET
          value: "minordetails-1aff3.appspot.com"
        # FIREBASE_SERVICE_ACCOUNT_KEY not needed with Workload Identity
```

### 3. Other Cloud Providers

**AWS ECS/Fargate:**
```json
{
  "environment": [
    {
      "name": "FIREBASE_SERVICE_ACCOUNT_KEY",
      "value": "{\"type\":\"service_account\",...}"
    },
    {
      "name": "FIREBASE_STORAGE_BUCKET", 
      "value": "minordetails-1aff3.appspot.com"
    }
  ]
}
```

## 🔒 Security Best Practices

### ✅ Do:
- Use environment variables for credentials
- Rotate service account keys regularly
- Use least-privilege IAM roles
- Monitor service account usage
- Use secrets management services in production

### ❌ Don't:
- Commit service account keys to version control
- Share keys in plain text (Slack, email, etc.)
- Use overly broad IAM permissions
- Log credentials in application logs
- Store keys in frontend code

## 🧪 Testing Your Setup

### 1. Verify Authentication
Start your server and check the console for initialization messages:
```
✅ "Firebase Admin SDK initialized with Service Account Key from environment variable."
✅ "Firebase Admin SDK initialized with GOOGLE_APPLICATION_CREDENTIALS."
❌ "WARNING: Signed URL generation might fail if credentials don't include private key."
```

### 2. Test Signed URL Generation
```bash
# Test the endpoint
curl -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  "http://localhost:8000/admin/device-requests/get-id-photo-url?object_path=employee_device_registration_identification/USER_ID/DEVICE_ID.jpg"
```

Expected response:
```json
{
  "signed_url": "https://storage.googleapis.com/bucket/path?X-Goog-Algorithm=..."
}
```

## 🐛 Troubleshooting

### Error: "you need a private key to sign credentials"
- **Cause**: Using user credentials instead of service account
- **Fix**: Set `FIREBASE_SERVICE_ACCOUNT_KEY` environment variable with service account JSON

### Error: "Invalid service account info"
- **Cause**: Malformed JSON in environment variable
- **Fix**: Ensure JSON is properly escaped and valid

### Error: "Permission denied"
- **Cause**: Service account lacks required permissions
- **Fix**: Add `Storage Object Admin` role to service account

### Error: "Bucket not found"
- **Cause**: Incorrect bucket name
- **Fix**: Verify `FIREBASE_STORAGE_BUCKET` environment variable

## 📝 Environment Variable Template

Create a `.env.template` file for your team:
```env
# Copy to .env and fill in your values (add .env to .gitignore!)
FIREBASE_SERVICE_ACCOUNT_KEY={"type":"service_account","project_id":"..."}
FIREBASE_STORAGE_BUCKET=your-project-id.appspot.com

# Optional: For local development with file
# FIREBASE_SERVICE_ACCOUNT_KEY_PATH=/path/to/serviceAccountKey.json
```

This setup ensures your credentials are secure, your application is production-ready, and your team can deploy safely across different environments! 