# Simple Admin Time Management API

This document outlines the three core admin time management operations for directly managing employee clock entries, plus tracking and viewing admin changes.

## Authentication

All endpoints require admin authentication. Include your admin auth token in the `Authorization` header.

## Base URL

All endpoints are prefixed with `/admin/time/`

---

## 1. CREATE a New Clock Entry Pair

**POST** `/admin/time/direct-clock-creation`

Creates a new clock-in/clock-out pair for any employee immediately. **This action is logged** in the admin change tracking system.

### Request Body
```json
{
  "employee_id": "firebase_uid_string",
  "day_of_punch": "2024-01-15",
  "new_start_time": "09:00",
  "new_end_time": "17:00",
  "dealership_id": "dealership_name_string",
  "reason": "Forgot to clock in/out"
}
```

### Response
```json
{
  "success": true,
  "message": "Clock entry created successfully",
  "clock_in_id": 123,
  "clock_out_id": 124,
  "employee_id": "firebase_uid_string",
  "start_time": "2024-01-15T09:00:00+00:00",
  "end_time": "2024-01-15T17:00:00+00:00",
  "reason": "Forgot to clock in/out",
  "created_by_admin": "admin_uid"
}
```

---

## 2. EDIT an Existing Clock Entry Pair

**POST** `/admin/time/direct-clock-edit`

Modifies an existing clock-in/clock-out pair. **This action is logged** in the admin change tracking system.

### Request Body
```json
{
  "employee_id": "firebase_uid_string",
  "original_clock_in_timelog_id": 123,
  "original_clock_out_timelog_id": 124,
  "day_of_punch": "2024-01-15",
  "new_start_time": "08:30",
  "new_end_time": "16:30",
  "dealership_id": "dealership_name_string",
  "reason": "Corrected punch times"
}
```

### Response
```json
{
  "success": true,
  "message": "Clock entry edited successfully",
  "clock_in_id": 123,
  "clock_out_id": 124,
  "employee_id": "firebase_uid_string",
  "original_start_time": "2024-01-15T09:00:00+00:00",
  "original_end_time": "2024-01-15T17:00:00+00:00",
  "new_start_time": "2024-01-15T08:30:00+00:00",
  "new_end_time": "2024-01-15T16:30:00+00:00",
  "reason": "Corrected punch times",
  "edited_by_admin": "admin_uid"
}
```

---

## 3. DELETE a Clock Entry Pair

**POST** `/admin/time/direct-clock-delete`

Permanently deletes a clock-in/clock-out pair. **This action is logged** in the admin change tracking system.

### Request Body
```json
{
  "employee_id": "firebase_uid_string",
  "clock_in_timelog_id": 123,
  "clock_out_timelog_id": 124,
  "reason": "Duplicate entry"
}
```

### Response
```json
{
  "success": true,
  "message": "Clock entry deleted successfully",
  "deleted_clock_in_id": 123,
  "deleted_clock_out_id": 124,
  "employee_id": "firebase_uid_string",
  "deleted_start_time": "2024-01-15T09:00:00+00:00",
  "deleted_end_time": "2024-01-15T17:00:00+00:00",
  "dealership_id": "dealership_name_string",
  "reason": "Duplicate entry",
  "deleted_by_admin": "admin_uid"
}
```

---

## 4. View Recent Admin Changes (Global Overview)

**GET** `/admin/time/recent-entries`

Retrieves a list of the most recent admin changes across all employees. This shows you a global overview of all CREATE, EDIT, and DELETE actions performed by admins.

### Query Parameters
- `limit` (integer, query, optional): Number of recent changes to return. Defaults to 50.

### Response
```json
{
  "recent_changes": [
    {
      "id": 15,
      "employee_id": "firebase_uid_string",
      "employee_name": "John Doe",
      "admin_id": "admin_uid",
      "admin_name": "Admin User",
      "action": "CREATE",
      "reason": "Forgot to clock in/out",
      "created_at": "2024-01-16T14:30:00+00:00",
      "clock_in_id": 125,
      "clock_out_id": 126,
      "dealership_id": "dealership_name_string",
      "start_time": "2024-01-16T09:00:00+00:00",
      "end_time": "2024-01-16T17:00:00+00:00",
      "original_start_time": null,
      "original_end_time": null,
      "punch_date": "2024-01-16",
      "date": "2024-01-16",
      "time": "14:30"
    },
    {
      "id": 14,
      "employee_id": "another_firebase_uid",
      "employee_name": "Jane Smith",
      "admin_id": "admin_uid",
      "admin_name": "Admin User",
      "action": "EDIT",
      "reason": "Corrected end time",
      "created_at": "2024-01-16T13:15:00+00:00",
      "clock_in_id": 123,
      "clock_out_id": 124,
      "dealership_id": "dealership_name_string",
      "start_time": "2024-01-15T09:00:00+00:00",
      "end_time": "2024-01-15T17:30:00+00:00",
      "original_start_time": "2024-01-15T09:00:00+00:00",
      "original_end_time": "2024-01-15T17:00:00+00:00",
      "punch_date": "2024-01-15",
      "date": "2024-01-16",
      "time": "13:15"
    }
  ]
}
```

---

## 5. View Admin Changes for Specific Employee

**GET** `/admin/time/employee/{employee_id}/changes`

Retrieves all admin changes for a specific employee. By default, it returns the 20 most recent changes.
To get **all** changes for an employee, send the query parameter `limit=0`.

### Query Parameters
- `employee_id` (string, path, required): Firebase UID of the employee.
- `limit` (integer, query, optional): Number of recent changes to return. Send `limit=0` to retrieve all changes for the employee. Defaults to 20 if not specified.

### Response
```json
{
  "employee_id": "firebase_uid_string",
  "admin_changes": [
    {
      "id": 15,
      "employee_id": "firebase_uid_string",
      "employee_name": "John Doe",
      "admin_id": "admin_uid",
      "admin_name": "Admin User",
      "action": "CREATE",
      "reason": "Forgot to clock in/out",
      "created_at": "2024-01-16T14:30:00+00:00",
      "clock_in_id": 125,
      "clock_out_id": 126,
      "dealership_id": "dealership_name_string",
      "start_time": "2024-01-16T09:00:00+00:00",
      "end_time": "2024-01-16T17:00:00+00:00",
      "original_start_time": null,
      "original_end_time": null,
      "punch_date": "2024-01-16",
      "date": "2024-01-16",
      "time": "14:30"
    }
  ]
}
```

---

## Helper Endpoint: Get Employee's Raw Punch Data

**GET** `/admin/time/employee/{employee_id}/recent-punches`

Retrieves the actual clock-in/out records from the TimeLog table for a specific employee. This is useful for selecting which entries to edit or delete.

### Query Parameters
- `employee_id` (string, path, required): Firebase UID of the employee.
- `limit` (integer, query, optional): Number of recent punches to return. Send `limit=0` to retrieve all punches for the employee. Defaults to 20 if not specified.

### Response
```json
{
  "employee_id": "firebase_uid_string",
  "recent_punches": [
    {
      "id": 123,
      "timestamp": "2024-01-15T09:00:00+00:00",
      "punch_type": "CLOCK_IN",
      "dealership_id": "dealership_name_string",
      "date": "2024-01-15",
      "time": "09:00"
    },
    {
      "id": 124,
      "timestamp": "2024-01-15T17:00:00+00:00",
      "punch_type": "CLOCK_OUT",
      "dealership_id": "dealership_name_string",
      "date": "2024-01-15",
      "time": "17:00"
    }
  ]
}
```

---

## Important Notes

1. **Time Format**: Use "HH:MM" format (24-hour)
2. **Date Format**: Use "YYYY-MM-DD" format  
3. **End time must be after start time**
4. **Both punch IDs must belong to the specified employee**
5. **Clock-in ID must be a CLOCK_IN punch, clock-out ID must be a CLOCK_OUT punch**
6. **All changes take effect immediately** - no approval process
7. **All actions are logged with the admin's UID for audit purposes**
8. **Admin changes are tracked separately** - you can see what was modified, when, by whom, and why

## Error Responses

- `400`: Invalid data (time format, end time before start time, etc.)
- `404`: Employee or punch IDs not found
- `403`: Insufficient admin permissions
- `500`: Unexpected server error

That's it! Three simple operations for complete clock entry management, plus full audit tracking of admin changes. 