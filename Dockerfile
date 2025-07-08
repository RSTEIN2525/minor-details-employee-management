# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application's code into the container at /app
COPY . .

# Set environment variables for CORS configuration
ENV DEV_DOMAIN=http://localhost:5173
ENV PRODUCTION_DOMAIN=https://minorautodetails.app
ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Make port 8080 available to the world outside this container
# Cloud Run sets the PORT environment variable, which Uvicorn will use when specified with --port
# EXPOSE 8080 # This is more for documentation; Cloud Run handles port exposure.

# Run main.py when the container launches
# Use the PORT environment variable that Cloud Run provides (defaults to 8080)
# If PORT is not set, fallback to 8000 for local development
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} 