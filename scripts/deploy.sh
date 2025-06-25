#!/bin/bash
# A simple script to run the three core deployment commands exactly as specified in the README.

set -e # Exit immediately if a command fails.

echo "--- 1. Building Docker image ---"
docker build --platform linux/amd64 -t gcr.io/minordetails-1aff3/employee-management-backend:latest .

echo "--- 2. Pushing Docker image to GCR ---"
docker push gcr.io/minordetails-1aff3/employee-management-backend:latest

echo "--- 3. Deploying to Google Cloud Run ---"
gcloud run deploy employee-management-backend \
   --image gcr.io/minordetails-1aff3/employee-management-backend:latest \
   --platform managed \
   --region us-central1 \
   --allow-unauthenticated \
   --add-cloudsql-instances minordetails-1aff3:us-east4:minor-details-clock-in-out-db \
   --set-env-vars "INSTANCE_CONNECTION_NAME=minordetails-1aff3:us-east4:minor-details-clock-in-out-db,DB_NAME=postgres,DB_USER=postgres,DB_PASSWORD=';(Ets?MBFK`^D`\>',VAPI_SECRET_TOKEN='kE7!pZ$r@N3qA*sV9bF2gH#jW1mX$yZ',INTERNAL_API_BASE_URL=https://employee-management-backend-507748767742.us-central1.run.app" \
   --quiet

echo "--- Deployment Complete ---" 