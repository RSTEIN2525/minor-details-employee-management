#!/bin/bash

# Employee Management Backend Deployment Script
# This script builds, pushes, and deploys the backend to Google Cloud Run,
# including all necessary environment variables for production and debugging.

set -e  # Exit immediately if a command exits with a non-zero status.

# --- Configuration ---
PROJECT_ID="minordetails-1aff3"
SERVICE_NAME="employee-management-backend"
REGION="us-central1"
IMAGE_NAME="gcr.io/${PROJECT_ID}/${SERVICE_NAME}:latest"

# Colors for clear output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}🚀 Starting deployment of Employee Management Backend...${NC}"

# --- Step 1: Build Docker image ---
echo -e "\n${YELLOW}🏗️  Step 1: Building Docker image for linux/amd64...${NC}"
docker build --platform linux/amd64 -t "${IMAGE_NAME}" .
echo -e "${GREEN}✅ Docker image built successfully.${NC}"

# --- Step 2: Push to Google Container Registry ---
echo -e "\n${YELLOW}📤 Step 2: Pushing image to Google Container Registry...${NC}"
docker push "${IMAGE_NAME}"
echo -e "${GREEN}✅ Image pushed successfully.${NC}"

# --- Step 3: Deploy to Cloud Run ---
echo -e "\n${YELLOW}🚀 Step 3: Deploying to Google Cloud Run with latest configuration...${NC}"
gcloud run deploy "${SERVICE_NAME}" \
    --image "${IMAGE_NAME}" \
    --platform managed \
    --region "${REGION}" \
    --allow-unauthenticated \
    --add-cloudsql-instances "minordetails-1aff3:us-east4:minor-details-clock-in-out-db" \
    --set-env-vars "INSTANCE_CONNECTION_NAME=minordetails-1aff3:us-east4:minor-details-clock-in-out-db,DB_NAME=postgres,DB_USER=postgres,DB_PASSWORD=';(Ets?MBFK`^D`\>',VAPI_SECRET_TOKEN='kE7!pZ$r@N3qA*sV9bF2gH#jW1mX$yZ',INTERNAL_API_BASE_URL=https://employee-management-backend-507748767742.us-central1.run.app" \
    --quiet

# Check if deployment was successful
if [ $? -eq 0 ]; then
    echo -e "\n${GREEN}✅ Deployment successful!${NC}"
    SERVICE_URL=$(gcloud run services describe ${SERVICE_NAME} --platform managed --region ${REGION} --format 'value(status.url)')
    echo -e "${GREEN}🌐 Your service is now available at:${NC} ${YELLOW}${SERVICE_URL}${NC}"
    echo -e "${GREEN}🔗 Vapi webhook endpoint:${NC} ${YELLOW}${SERVICE_URL}/api/vapi-webhook${NC}"
else
    echo -e "\n${RED}❌ Deployment failed. Please check the logs above for errors.${NC}"
    exit 1
fi

echo -e "\n${GREEN}🎉 Deployment completed successfully!${NC}" 