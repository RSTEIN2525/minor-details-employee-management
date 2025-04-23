import firebase_admin
from firebase_admin import firestore, auth as firebase_auth

# Initialize the Admin SDK using Application Default Credentials
firebase_admin.initialize_app()

# Expose the Firestore client and the ID-token verifier
db = firestore.client()
verify_id_token = firebase_auth.verify_id_token
