# New Shift Change Endpoints

## Overview

Added two new endpoints to the existing `/admin/shift-changes/` route for better shift change management.

---

## Endpoint 1: Recent Shift Changes

### **GET** `/admin/shift-changes/recent?limit=10`

Get the most recent shift changes (defaults to last 10).

#### Query Parameters
- `limit` (optional): Number of results to return (default: 10)

#### Response Structure
Returns an array of `ShiftChangeResponse` objects:

```json
[
  {
    "id": 123,
    "employee_id": "employee_uuid",
    "employee_name": "John Doe",
    "created_by_owner_id": "owner_uuid", 
    "created_by_owner_name": "Manager Name",
    "change_type": "schedule_change",
    "effective_date": "2024-01-15",
    "reason": "Employee requested time change",
    "notes": "Approved by manager",
    "original_start_time": "09:00",
    "original_end_time": "17:00",
    "original_dealership_id": "dealership_uuid",
    "new_start_time": "10:00", 
    "new_end_time": "18:00",
    "new_dealership_id": "dealership_uuid",
    "swap_with_employee_id": null,
    "swap_with_employee_name": null,
    "created_at": "2024-01-10T14:30:00Z",
    "status": "approved",
    "employee_notified": true,
    "employee_viewed_at": "2024-01-10T15:00:00Z"
  }
]
```

#### Usage Examples
- `GET /admin/shift-changes/recent` - Get last 10 shift changes
- `GET /admin/shift-changes/recent?limit=5` - Get last 5 shift changes
- `GET /admin/shift-changes/recent?limit=25` - Get last 25 shift changes

---

## Endpoint 2: Search Employee Shift Changes

### **GET** `/admin/shift-changes/search/employee/{employee_id}`

Search for all shift changes for a specific employee with optional filters.

#### Path Parameters
- `employee_id`: The UUID of the employee to search for

#### Query Parameters
- `limit` (optional): Maximum number of results (no limit if not specified)
- `include_past` (optional): Whether to include past shift changes (default: true)
- `change_type` (optional): Filter by specific change type

#### Change Types Available
- `schedule_change` - Change scheduled hours
- `location_change` - Change dealership/location  
- `shift_swap` - Swap shifts between employees
- `overtime_assignment` - Assign overtime
- `time_off_adjustment` - Adjust time off

#### Response Structure
Returns an array of `ShiftChangeResponse` objects (same structure as above).

#### Usage Examples
- `GET /admin/shift-changes/search/employee/abc-123` - Get all shift changes for employee abc-123
- `GET /admin/shift-changes/search/employee/abc-123?limit=20` - Get last 20 shift changes for employee
- `GET /admin/shift-changes/search/employee/abc-123?include_past=false` - Get only future/current shift changes
- `GET /admin/shift-changes/search/employee/abc-123?change_type=schedule_change` - Get only schedule changes
- `GET /admin/shift-changes/search/employee/abc-123?limit=10&change_type=shift_swap&include_past=false` - Get last 10 future shift swaps

---

## Authentication

Both endpoints require admin authentication using the existing `require_admin_role` dependency.

## Key Features

### Recent Endpoint
- ✅ Simple way to see the latest activity across all employees
- ✅ Configurable limit for performance
- ✅ Ordered by creation time (newest first)
- ✅ Includes all employee and owner names for easy reading

### Search Endpoint  
- ✅ Find all shift changes for a specific employee
- ✅ Optional filtering by change type
- ✅ Can exclude past changes to see only future/active ones
- ✅ Flexible limit control
- ✅ Rich response data with all related names populated

## Integration Notes

These endpoints complement the existing shift change endpoints:
- `/admin/shift-changes/all` - Get all shift changes with basic filtering
- `/admin/shift-changes/employee/{employee_id}` - Get employee shift changes (simpler version)
- `/admin/shift-changes/upcoming` - Get upcoming shift changes

The new endpoints provide more focused and flexible access patterns for common admin tasks. 