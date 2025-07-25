from typing import Annotated  # Use typing.Annotated for Python 3.9+

from fastapi import Depends, Header, HTTPException, Request, status
from firebase_admin import auth as firebase_auth
from firebase_admin import firestore

from core.firebase import db as firestore_client
from core.firebase import verify_id_token
from db.session import get_session

# Specific exception for device trust issues
DEVICE_TRUST_EXCEPTION = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Device not registered or not trusted.",
)

# Standard credentials exception
CREDENTIALS_EXCEPTION = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)
# Admin Roles Defined
ADMIN_ROLES = ["owner"]

# Supervisor SubRoles Defined
SUPERVISOR_SUBROLES = ["minorDetailsSupervisor"]


# Advaned Check Matches Device ID / Pulled User Profile
async def get_current_user(
    request: Request,
    x_device_id: Annotated[str | None, Header(alias="X-Device-Id")] = None,
):

    # 1) Extract & Analyze Authorization Header
    auth_header = request.headers.get("Authorization", "")

    # Make Sure Formatting Valid
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    # Extract Users/______ from Authorization Header
    token = auth_header.split(" ", 1)[1]

    # 2) Verify This Points to a Real User Account
    try:

        # Firebase.py Helper
        decoded = verify_id_token(token)

    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )
    uid = decoded.get("uid")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Token did not contain uid"
        )

    # 3) Fetch the Firestore user profile
    doc_ref = firestore_client.collection("users").document(uid)
    snapshot = doc_ref.get()
    if not snapshot.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User profile not found in Firestore",
        )
    profile = snapshot.to_dict()

    # Trusted Device Check
    if x_device_id:
        print(f"🔍 DEVICE VALIDATION DEBUG for user {uid}:")
        print(f"📱 Client sent device ID: '{x_device_id}'")

        # Initialize User's Trusted Devices
        trusted_devices = profile.get("devices", [])
        print(f"💾 User's registered devices: {trusted_devices}")
        print(f"📊 Number of registered devices: {len(trusted_devices)}")

        # Ensure Formatting Of List Is Correct
        if not isinstance(trusted_devices, list):

            # Error Message
            print(
                f"Data integrity error: 'devices' field for user {uid} is not a list."
            )
            raise DEVICE_TRUST_EXCEPTION

        # The device ID sent by the client is not in the user's trusted list.
        if x_device_id not in trusted_devices:
            print(f"❌ DEVICE NOT FOUND: '{x_device_id}' not in {trusted_devices}")
            print(f"🔧 Exact string comparison failed")

            # Debug: Check for any similar device IDs (case insensitive)
            similar_devices = [
                d for d in trusted_devices if d.lower() == x_device_id.lower()
            ]
            if similar_devices:
                print(
                    f"⚠️ CASE MISMATCH: Found similar device with different case: {similar_devices}"
                )

            # Debug: Check for partial matches
            partial_matches = [
                d for d in trusted_devices if x_device_id in d or d in x_device_id
            ]
            if partial_matches:
                print(f"⚠️ PARTIAL MATCH: Found partial matches: {partial_matches}")

            raise DEVICE_TRUST_EXCEPTION
        else:
            print(f"✅ DEVICE VALIDATED: '{x_device_id}' found in registered devices")
    else:
        print(
            f"⚠️ NO DEVICE ID: X-Device-Id header not provided by client for user {uid}"
        )

    # 4) Extract their shops list
    # Get the raw strings from both Firestore fields
    raw_dealerships = profile.get("dealerships", "")
    raw_time_clock_dealerships = profile.get("timeClockDealerships", "")

    # Combine the strings, then split, strip, and find unique values
    combined_raw = raw_dealerships + "," + raw_time_clock_dealerships
    dealerships = list(set(s.strip() for s in combined_raw.split(",") if s.strip()))

    # Extract Critical Information
    name = profile.get("displayName", "")
    email = profile.get("email", "")
    role = profile.get("role", "")
    subRole = profile.get("subRole", "")

    return {
        "uid": uid,
        "name": name,
        "email": email,
        "dealerships": dealerships,
        "role": role,
        "subRole": subRole,
    }


# Basic Check Matches Firebase Auth Token
async def get_current_user_basic_auth(request: Request):
    # 1) Extract & Analyze Authorization Header (Same as before)
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise CREDENTIALS_EXCEPTION
    token = auth_header.split(" ", 1)[1]

    # 2) Verify Firebase Token (Same as before)
    try:
        decoded = verify_id_token(token)
    except Exception:
        raise CREDENTIALS_EXCEPTION
    uid = decoded.get("uid")
    if not uid:
        raise CREDENTIALS_EXCEPTION

    # 3) Fetch the Firestore user profile (Same as before)
    try:
        doc_ref = firestore_client.collection("users").document(uid)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found in Firestore",
            )
        profile = snapshot.to_dict()
    except Exception as e:
        print(f"Firestore error fetching profile for {uid}: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Could not fetch user profile.",
        )

    # 4) NO Device Trust Check in this version

    # 5) Extract remaining profile information (Same as before)
    raw_dealerships = profile.get("dealerships", "")
    dealerships = [s.strip() for s in raw_dealerships.split(",") if s.strip()]
    name = profile.get("displayName", "")
    email = profile.get("email", "")
    role = profile.get("role", "")

    # Return the validated user profile data
    return {
        "uid": uid,
        "name": name,
        "email": email,
        "dealerships": dealerships,
        "role": role,
    }


# Admin Role Check Dependency
async def require_admin_role(
    current_user: Annotated[dict, Depends(get_current_user_basic_auth)]
):
    # Pull Role Field
    user_role = current_user.get("role")

    # Check That User Has Adequate Permissions
    if not user_role in ADMIN_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User doesn't have sufficient privileges for this action",
        )

    # Passes Check Endpoint
    return current_user


# Alias for backward compatibility
require_user = get_current_user_basic_auth


# Function to verify admin role from token (for Vapi webhook)
def require_admin_role_from_token(token: str) -> dict:
    """Verify admin role from a Firebase token string"""
    try:
        decoded = verify_id_token(token)
        uid = decoded.get("uid")
        if not uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token did not contain uid",
            )

        # Fetch the Firestore user profile
        doc_ref = firestore_client.collection("users").document(uid)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found in Firestore",
            )
        profile = snapshot.to_dict()

        # Check admin role
        user_role = profile.get("role", "")
        if user_role not in ADMIN_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User doesn't have sufficient privileges for this action",
            )

        # Extract profile information
        raw_dealerships = profile.get("dealerships", "")
        dealerships = [s.strip() for s in raw_dealerships.split(",") if s.strip()]

        return {
            "uid": uid,
            "name": profile.get("displayName", ""),
            "email": profile.get("email", ""),
            "dealerships": dealerships,
            "role": user_role,
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
        )


def require_supervisor_role(current_user: dict = Depends(get_current_user)):
    """
    Dependency that ensures the current user has supervisor privileges.
    Allows users with subRole == "minorDetailsSupervisor" to access the endpoint.
    """
    # This uid is the Firebase Auth UID, which is used as the Firestore document ID
    uid = current_user.get("uid")

    # Pull Role Field
    user_role = current_user.get("role")

    # Pull SubRole Field (this is where supervisor info is stored)
    user_sub_role = current_user.get("subRole")

    # Check if user has supervisor privileges
    if user_sub_role in SUPERVISOR_SUBROLES:
        return current_user

    # If not a supervisor, check if they're an admin (admins can access everything)
    if user_role in ADMIN_ROLES:
        return current_user

    # If neither supervisor nor admin, deny access
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient privileges. Supervisor or admin role required.",
    )


def require_admin_or_supervisor_role(current_user: dict = Depends(get_current_user)):
    """
    Dependency that allows both admins and supervisors to access an endpoint.
    This is a convenience function that combines both checks.
    """
    # This uid is the Firebase Auth UID, which is used as the Firestore document ID
    uid = current_user.get("uid")

    # Pull Role Field
    user_role = current_user.get("role")

    # Pull SubRole Field
    user_sub_role = current_user.get("subRole")

    print(f"🔍 ADMIN OR SUPERVISOR ROLE CHECK: {user_role} {user_sub_role}")

    # Check if user has supervisor privileges
    if user_sub_role in SUPERVISOR_SUBROLES:
        return current_user

    # Check if user has admin privileges
    if user_role in ADMIN_ROLES:
        return current_user

    # If neither supervisor nor admin, deny access
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Insufficient privileges. Supervisor or admin role required.",
    )
