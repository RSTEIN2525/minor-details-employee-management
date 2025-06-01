# Admin Time Management Endpoints

## Overview

We've implemented the requested admin endpoints for direct time clock management. These endpoints allow owners/admins to create and edit employee time entries without going through the approval workflow.

## Implementation Details

### Base URL Structure
All endpoints are prefixed with `/admin/time/`

### Authentication
All endpoints require admin authentication using the existing `require_admin_role` dependency.

---

## Endpoint 1: Admin Clock Creation

### **POST** `/admin/time/direct-clock-creation`

Creates a new clock-in/out pair for a specified employee immediately (no approval process).

#### Request Body Structure
```json
{
  "employee_id": "string",
  "day_of_punch": "YYYY-MM-DD", 
  "new_start_time": "HH:MM",
  "new_end_time": "HH:MM",
  "dealership_id": "string",
  "reason": "string"
}
```

#### Response Structure
```json
{
  "success": true,
  "message": "Clock entry created successfully",
  "clock_in_id": 123,
  "clock_out_id": 124,
  "employee_id": "employee_uuid",
  "start_time": "2024-01-15T09:00:00+00:00",
  "end_time": "2024-01-15T17:00:00+00:00", 
  "reason": "Forgot to clock in",
  "created_by_admin": "admin_uid"
}
```

---

## Endpoint 2: Admin Clock Edit

### **POST** `/admin/time/direct-clock-edit`

Edits an existing clock-in/out pair for a specified employee immediately (no approval process).

#### Request Body Structure
```json
{
  "employee_id": "string",
  "original_clock_in_timelog_id": 123,
  "original_clock_out_timelog_id": 124,
  "day_of_punch": "YYYY-MM-DD",
  "new_start_time": "HH:MM", 
  "new_end_time": "HH:MM",
  "dealership_id": "string",
  "reason": "string"
}
```

#### Response Structure
```json
{
  "success": true,
  "message": "Clock entry edited successfully",
  "clock_in_id": 123,
  "clock_out_id": 124,
  "employee_id": "employee_uuid",
  "original_start_time": "2024-01-15T08:30:00+00:00",
  "original_end_time": "2024-01-15T16:30:00+00:00",
  "new_start_time": "2024-01-15T09:00:00+00:00",
  "new_end_time": "2024-01-15T17:00:00+00:00",
  "reason": "Corrected punch times",
  "edited_by_admin": "admin_uid"
}
```

---

## Helper Endpoint: Get Employee Recent Punches

### **GET** `/admin/time/employee/{employee_id}/recent-punches?limit=20`

Retrieves recent punch entries for a specific employee to help with the editing interface.

#### Response Structure
```json
{
  "employee_id": "employee_uuid",
  "recent_punches": [
    {
      "id": 123,
      "timestamp": "2024-01-15T09:00:00+00:00",
      "punch_type": "clock_in", 
      "dealership_id": "dealership_uuid",
      "date": "2024-01-15",
      "time": "09:00"
    },
    {
      "id": 124,
      "timestamp": "2024-01-15T17:00:00+00:00", 
      "punch_type": "clock_out",
      "dealership_id": "dealership_uuid",
      "date": "2024-01-15",
      "time": "17:00"
    }
  ]
}
```

---

## Key Differences from Employee Endpoints

1. **No Approval Workflow**: These endpoints directly modify `TimeLog` entries instead of creating `ClockRequestLog` entries
2. **Employee Selection**: All endpoints require an `employee_id` field to specify which employee the action applies to
3. **Immediate Effect**: Changes take effect immediately and are reflected in all analytics/reporting
4. **Admin Tracking**: All actions are logged with the admin's UID for audit purposes

## Validation Rules

### Time Validation
- End time must be after start time
- Time format: HH:MM (24-hour format)
- Date bounds: Cannot be more than 365 days in the past or 7 days in the future

### Employee Validation  
- Employee ID must exist
- Admin must have permissions to modify the employee's records (currently all admins can modify any employee)
- Original punch IDs must belong to the specified employee (for edits)

### Punch Type Validation (for edits)
- `original_clock_in_timelog_id` must reference a CLOCK_IN punch
- `original_clock_out_timelog_id` must reference a CLOCK_OUT punch

## Error Responses

All endpoints return standard HTTP error codes with descriptive messages:

- `400 Bad Request`: Invalid data (time format, logical errors, etc.)
- `403 Forbidden`: Insufficient admin permissions
- `404 Not Found`: Employee or punch IDs not found
- `500 Internal Server Error`: Unexpected server errors

Example error response:
```json
{
  "detail": "End time must be after start time."
}
```

## Implementation Notes

### Backend Architecture
- Built using the same patterns as existing admin endpoints
- Reuses the existing `combine_date_time_str` helper function
- Uses the same `require_admin_role` authentication dependency
- Follows the established error handling patterns

### Database Impact
- Direct manipulation of `TimeLog` table
- No entries created in `ClockRequestLog` table  
- Changes are immediately reflected in all existing analytics endpoints

### Audit Trail
- Admin UID is captured and returned in responses
- Consider implementing a separate audit log table if detailed tracking is required

---

## Ready to Use

These endpoints are now live and ready for frontend integration. The implementation follows the exact patterns established by your existing employee-facing endpoints but with the administrative privileges and employee selection capabilities you requested. 