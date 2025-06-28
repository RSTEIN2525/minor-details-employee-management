#!/bin/bash

# This script automates the deployment of the FastAPI application to Google Cloud Run.
# It follows the steps outlined in the README.md file.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Starting deployment process..."

# Check if OPENAI_API_KEY environment variable is set
if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY environment variable is not set."
    echo "Please set it with: export OPENAI_API_KEY='your-api-key-here'"
    exit 1
fi

# Step 1 (README Step 2): Build the Docker Image
# Build for linux/amd64 platform as required by Cloud Run.
echo "Step 1/3: Building Docker image..."
docker build --platform linux/amd64 -t gcr.io/minordetails-1aff3/employee-management-backend:latest .
echo "Docker image built successfully."

# Step 2 (README Step 3): Push the Docker Image to Google Container Registry (GCR)
echo "Step 2/3: Pushing Docker image to GCR..."
docker push gcr.io/minordetails-1aff3/employee-management-backend:latest
echo "Docker image pushed to GCR successfully."

# Step 3 (README Step 4): Deploy to Google Cloud Run
echo "Step 3/3: Deploying to Google Cloud Run..."
gcloud run deploy employee-management-backend \
    --image gcr.io/minordetails-1aff3/employee-management-backend:latest \
    --platform managed \
    --region us-central1 \
    --allow-unauthenticated \
    --add-cloudsql-instances minordetails-1aff3:us-east4:minor-details-clock-in-out-db \
    --set-env-vars INSTANCE_CONNECTION_NAME=minordetails-1aff3:us-east4:minor-details-clock-in-out-db,DB_NAME=postgres,DB_USER=postgres,DB_PASSWORD=';(Ets?MBFK`^D`\>',VAPI_SECRET_TOKEN='kE7!pZ$r@N3qA*sV9bF2gH#jW1mX$yZ',INTERNAL_API_BASE_URL=https://employee-management-backend-507748767742.us-central1.run.app,OPENAI_API_KEY="$OPENAI_API_KEY" \
    --quiet
echo "Deployment to Google Cloud Run successful."

echo "Deployment script finished." 