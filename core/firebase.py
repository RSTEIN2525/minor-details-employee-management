import firebase_admin
from firebase_admin import credentials, firestore, auth as firebase_auth
import os
import json
import tempfile
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def initialize_firebase():
    """Initialize Firebase Admin SDK with production-ready credential handling"""
    
    # Method 1: Service Account Key from Environment Variable (Recommended for production)
    service_account_key_json = os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY')

    if service_account_key_json:
        try:
            # Parse the JSON string from environment variable
            service_account_info = json.loads(service_account_key_json)
            cred = credentials.Certificate(service_account_info)
            firebase_admin.initialize_app(cred, {
                'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET', 'minordetails-1aff3.appspot.com')
            })
            print("Firebase Admin SDK initialized with Service Account Key from environment variable.")
            return
        except (json.JSONDecodeError, Exception) as e:
            print(f"Error parsing FIREBASE_SERVICE_ACCOUNT_KEY: {e}")
    
    # Method 2: Service Account Key File (for local development only)
    service_account_key_path = os.getenv('FIREBASE_SERVICE_ACCOUNT_KEY_PATH')
    if service_account_key_path and os.path.exists(service_account_key_path):
        cred = credentials.Certificate(service_account_key_path)
        firebase_admin.initialize_app(cred, {
            'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET', 'minordetails-1aff3.appspot.com')
        })
        print("Firebase Admin SDK initialized with Service Account Key from file path.")
        return
    
    # Method 3: GOOGLE_APPLICATION_CREDENTIALS (Cloud environments)
    if os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
        firebase_admin.initialize_app(options={
            'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET', 'minordetails-1aff3.appspot.com')
        })
        print("Firebase Admin SDK initialized with GOOGLE_APPLICATION_CREDENTIALS.")
        return
    
    # Method 4: Default Application Default Credentials (fallback)
    firebase_admin.initialize_app(options={
        'storageBucket': os.getenv('FIREBASE_STORAGE_BUCKET', 'minordetails-1aff3.appspot.com')
    })
    print("Firebase Admin SDK initialized with default Application Default Credentials.")
    print("WARNING: Signed URL generation might fail if credentials don't include private key.")

# Initialize Firebase
initialize_firebase()

# Expose the Firestore client and the ID-token verifier
db = firestore.client()
verify_id_token = firebase_auth.verify_id_token
