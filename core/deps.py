from fastapi import Depends, HTTPException, Request, status
from firebase_admin import auth as firebase_auth, firestore
from core.firebase import verify_id_token, db as firestore_client

async def get_current_user(request: Request):

    # 1) Extract & Analyze Authorization Header
    auth_header = request.headers.get("Authorization", "")

    # Make Sure Formatting Valid
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Missing or invalid Authorization header")
    
    # Extract Users/______ from Authorization Header
    token = auth_header.split(" ", 1)[1]

    # 2) Verify This Points to a Real User Account
    try:

        # Firebase.py Helper
        decoded = verify_id_token(token)


    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Invalid or expired token")
    uid = decoded.get("uid")
    if not uid:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Token did not contain uid")

    # 3) Fetch the Firestore user profile
    doc_ref = firestore_client.collection("users").document(uid)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="User profile not found in Firestore")
    profile = snapshot.to_dict()

    # 4) Extract their shops list
    raw = profile.get("dealerships", "")  # Firestore field name
    dealerships = [s.strip() for s in raw.split(",") if s.strip()]

    # Extract Critical Information
    name = profile.get("displayName","")
    email = profile.get("email","")
    role = profile.get("role","")

    return {
        "uid": uid,
        "name": name,
        "email": email,
        "dealerships": dealerships,
        "role" : role
    }