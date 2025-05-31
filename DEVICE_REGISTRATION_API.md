# Device Registration API Documentation

## Overview

The device registration system has been updated with two new requirements:

1. **ID Photo Upload**: Users must upload a photo of their ID document
2. **New Device ID Format**: Device IDs must follow the format `phone_number + device_type`

## API Endpoint

### POST `/device/register`

**Content-Type**: `multipart/form-data`

**Authorization**: Bearer token required

#### Request Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `device_id` | string (form field) | Yes | Device identifier in format: `phone_number + device_type` |
| `id_photo` | file (form field) | Yes | Photo of user's ID document |

#### Device ID Format

The `device_id` must be a combination of:
- **Phone number**: 10-15 digits (no spaces, dashes, or special characters)
- **Device type**: One of the following (case-insensitive):
  - `iphone`
  - `android` 
  - `ios`
  - `web`

**Valid Examples:**
- `4435713151iphone`
- `5551234567android`
- `12345678901web`

**Invalid Examples:**
- `443-571-3151iphone` (contains dashes)
- `4435713151unknowndevice` (invalid device type)
- `443iphone` (phone number too short)

#### ID Photo Requirements

- **Supported formats**: JPEG, JPG, PNG, WEBP
- **Maximum file size**: 5MB
- **Content**: Must be a clear photo of a government-issued ID document

#### Example Request (cURL)

```bash
curl -X POST "https://your-domain.com/device/register" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -F "device_id=4435713151iphone" \
  -F "id_photo=@/path/to/id_photo.jpg"
```

#### Example Request (JavaScript/Fetch)

```javascript
const formData = new FormData();
formData.append('device_id', '4435713151iphone');
formData.append('id_photo', fileInput.files[0]); // File from input element

const response = await fetch('/device/register', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${userToken}`
  },
  body: formData
});

const result = await response.json();
```

#### Success Response (202 Accepted)

```json
{
  "status": "submitted",
  "message": "Device registration request submitted for approval.",
  "device_id": "4435713151iphone",
  "phone_number": "4435713151"
}
```

#### Error Responses

**400 Bad Request - Invalid Device ID Format:**
```json
{
  "detail": "Invalid device ID format. Expected format: phone_number + device_type (e.g., '4435713151iphone')"
}
```

**400 Bad Request - Invalid File Type:**
```json
{
  "detail": "Invalid file type. Allowed types: image/jpeg, image/jpg, image/png, image/webp"
}
```

**400 Bad Request - File Too Large:**
```json
{
  "detail": "File size exceeds 5MB limit"
}
```

**400 Bad Request - Missing ID Photo:**
```json
{
  "detail": "ID photo is required for device registration."
}
```

**202 Accepted - Existing Pending Request:**
```json
{
  "status": "pending",
  "message": "Device registration request is already pending approval."
}
```

## Frontend Implementation Notes

1. **Form Handling**: Use `FormData` for multipart form submissions
2. **File Validation**: Validate file type and size on the client side for better UX
3. **Device ID Generation**: Combine user's phone number with detected device type
4. **Progress Indication**: Show upload progress for better user experience

## Database Schema Changes

The `deviceRequests` collection now includes these additional fields:

- `phoneNumber`: Extracted phone number from device ID
- `idPhotoUrl`: Public URL to the uploaded ID photo in Firebase Storage

## Firebase Storage Setup

Ensure your Firebase Storage bucket is properly configured:

1. Set the `FIREBASE_STORAGE_BUCKET` environment variable
2. Configure appropriate security rules for the `device_registrations/` path
3. Ensure the service account has Storage Admin permissions

## Admin Dashboard Updates

Admin users can now view:
- Phone numbers extracted from device IDs
- Uploaded ID photos via the `idPhotoUrl` field
- All new fields are included in the device request history responses 