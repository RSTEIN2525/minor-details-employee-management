# Shift Change API Documentation

## Overview

The shift change system allows **owners only** to create and manage shift changes for employees. All shift changes are automatically approved when created by owners. Employees can view their shift changes but cannot create or request them.

## Key Features

- ✅ **Owner-only creation**: Only users with admin/owner role can create shift changes
- ✅ **Auto-approval**: All shift changes are automatically approved
- ✅ **Multiple change types**: Schedule changes, location changes, shift swaps, overtime assignments, etc.
- ✅ **Employee notifications**: Employees can view and mark changes as viewed
- ✅ **Comprehensive tracking**: Full audit trail of who created what and when

## Shift Change Types

```typescript
enum ShiftChangeType {
  SCHEDULE_CHANGE = "schedule_change",      // Change scheduled hours
  LOCATION_CHANGE = "location_change",      // Change dealership/location  
  SHIFT_SWAP = "shift_swap",               // Swap shifts between employees
  OVERTIME_ASSIGNMENT = "overtime_assignment", // Assign overtime
  TIME_OFF_ADJUSTMENT = "time_off_adjustment"  // Adjust time off
}
```

---

## Admin/Owner API Endpoints

### 1. Create Shift Change

**POST** `/admin/shift-changes/create`

**Authorization**: Admin/Owner role required

**Request Body**:
```json
{
  "employee_id": "user123",
  "change_type": "schedule_change",
  "effective_date": "2024-01-15",
  "reason": "Customer request for earlier start time",
  "notes": "Employee agreed to the change",
  "original_start_time": "09:00",
  "original_end_time": "17:00", 
  "original_dealership_id": "dealership1",
  "new_start_time": "08:00",
  "new_end_time": "16:00",
  "new_dealership_id": "dealership1",
  "swap_with_employee_id": null
}
```

**Response**:
```json
{
  "id": 1,
  "employee_id": "user123",
  "employee_name": "John Doe",
  "created_by_owner_id": "owner456",
  "created_by_owner_name": "Jane Smith",
  "change_type": "schedule_change",
  "effective_date": "2024-01-15",
  "reason": "Customer request for earlier start time",
  "notes": "Employee agreed to the change",
  "original_start_time": "09:00",
  "original_end_time": "17:00",
  "original_dealership_id": "dealership1",
  "new_start_time": "08:00", 
  "new_end_time": "16:00",
  "new_dealership_id": "dealership1",
  "swap_with_employee_id": null,
  "swap_with_employee_name": null,
  "created_at": "2024-01-10T10:30:00Z",
  "status": "approved",
  "employee_notified": false,
  "employee_viewed_at": null
}
```

### 2. Get All Shift Changes

**GET** `/admin/shift-changes/all`

**Query Parameters**:
- `limit` (int, default: 50): Number of results to return
- `offset` (int, default: 0): Pagination offset
- `employee_id` (string, optional): Filter by specific employee
- `effective_date` (date, optional): Filter by effective date

**Response**: Array of shift change objects

### 3. Get Employee's Shift Changes

**GET** `/admin/shift-changes/employee/{employee_id}`

**Query Parameters**:
- `limit` (int, default: 20): Number of results to return

**Response**: Array of shift change objects for the specified employee

### 4. Get Upcoming Shift Changes

**GET** `/admin/shift-changes/upcoming`

**Query Parameters**:
- `days_ahead` (int, default: 7): Number of days to look ahead

**Response**: Array of upcoming shift changes

### 5. Delete Shift Change

**DELETE** `/admin/shift-changes/{shift_change_id}`

**Response**:
```json
{
  "status": "success",
  "message": "Shift change 1 deleted successfully."
}
```

---

## Employee/User API Endpoints

### 1. Get My Shift Changes

**GET** `/shift-changes/my-changes`

**Query Parameters**:
- `limit` (int, default: 20): Number of results to return
- `include_past` (bool, default: true): Include past shift changes

**Response**: Array of user shift change objects (simplified view)

### 2. Get My Upcoming Shift Changes

**GET** `/shift-changes/upcoming`

**Query Parameters**:
- `days_ahead` (int, default: 14): Number of days to look ahead

**Response**: Array of upcoming shift changes for the authenticated user

### 3. Get My Unviewed Shift Changes

**GET** `/shift-changes/unviewed`

**Response**: Array of unviewed shift changes

### 4. Mark Shift Change as Viewed

**POST** `/shift-changes/{shift_change_id}/mark-viewed`

**Response**:
```json
{
  "status": "success",
  "message": "Shift change marked as viewed.",
  "viewed_at": "2024-01-10T15:30:00Z"
}
```

### 5. Mark All Shift Changes as Viewed

**POST** `/shift-changes/mark-all-viewed`

**Response**:
```json
{
  "status": "success", 
  "message": "Marked 3 shift changes as viewed.",
  "viewed_count": 3
}
```

### 6. Get Shift Change Summary

**GET** `/shift-changes/summary`

**Response**:
```json
{
  "total_changes": 15,
  "unviewed_changes": 2,
  "upcoming_changes": 3,
  "recent_changes": [
    {
      "id": 1,
      "change_type": "schedule_change",
      "effective_date": "2024-01-15",
      "reason": "Customer request for earlier start time",
      "notes": "Employee agreed to the change",
      "original_start_time": "09:00",
      "original_end_time": "17:00",
      "new_start_time": "08:00",
      "new_end_time": "16:00",
      "created_at": "2024-01-10T10:30:00Z",
      "created_by_owner_name": "Jane Smith",
      "employee_viewed_at": null
    }
  ]
}
```

---

## Common Use Cases

### 1. Schedule Change
```json
{
  "employee_id": "user123",
  "change_type": "schedule_change",
  "effective_date": "2024-01-15",
  "reason": "Customer request",
  "original_start_time": "09:00",
  "original_end_time": "17:00",
  "new_start_time": "08:00", 
  "new_end_time": "16:00"
}
```

### 2. Location Change
```json
{
  "employee_id": "user123",
  "change_type": "location_change", 
  "effective_date": "2024-01-15",
  "reason": "Staffing needs at different location",
  "original_dealership_id": "dealership1",
  "new_dealership_id": "dealership2"
}
```

### 3. Shift Swap
```json
{
  "employee_id": "user123",
  "change_type": "shift_swap",
  "effective_date": "2024-01-15", 
  "reason": "Employee requested swap",
  "swap_with_employee_id": "user456",
  "original_start_time": "09:00",
  "original_end_time": "17:00",
  "new_start_time": "13:00",
  "new_end_time": "21:00"
}
```

### 4. Overtime Assignment
```json
{
  "employee_id": "user123",
  "change_type": "overtime_assignment",
  "effective_date": "2024-01-15",
  "reason": "High workload this week",
  "original_end_time": "17:00",
  "new_end_time": "19:00"
}
```

---

## Data Models

### ShiftChange (Database Model)
```typescript
interface ShiftChange {
  id: number;
  employee_id: string;
  created_by_owner_id: string;
  change_type: ShiftChangeType;
  effective_date: string; // ISO date
  reason: string;
  notes?: string;
  
  // Original shift details
  original_start_time?: string; // "HH:MM"
  original_end_time?: string;   // "HH:MM"
  original_dealership_id?: string;
  
  // New shift details  
  new_start_time?: string;      // "HH:MM"
  new_end_time?: string;        // "HH:MM"
  new_dealership_id?: string;
  
  // For shift swaps
  swap_with_employee_id?: string;
  
  // Metadata
  created_at: string;           // ISO datetime
  status: string;               // Always "approved"
  employee_notified: boolean;
  employee_viewed_at?: string;  // ISO datetime
}
```

### UserShiftChangeResponse (Employee View)
```typescript
interface UserShiftChangeResponse {
  id: number;
  change_type: ShiftChangeType;
  effective_date: string;
  reason: string;
  notes?: string;
  
  original_start_time?: string;
  original_end_time?: string;
  original_dealership_id?: string;
  
  new_start_time?: string;
  new_end_time?: string;
  new_dealership_id?: string;
  
  swap_with_employee_id?: string;
  swap_with_employee_name?: string;
  
  created_at: string;
  created_by_owner_name?: string;
  employee_viewed_at?: string;
}
```

---

## Error Responses

### 400 Bad Request
```json
{
  "detail": "Invalid time format: 25:00. Use HH:MM format."
}
```

### 403 Forbidden  
```json
{
  "detail": "You can only mark your own shift changes as viewed."
}
```

### 404 Not Found
```json
{
  "detail": "Employee with ID user123 not found."
}
```

---

## Frontend Integration Notes

### For Owner Dashboard:
1. **Create Shift Changes**: Use the admin endpoints to create various types of shift changes
2. **View All Changes**: Display all shift changes with filtering and pagination
3. **Employee Management**: View shift changes per employee
4. **Upcoming Changes**: Show upcoming changes for planning

### For Employee Portal:
1. **View My Changes**: Show employee their shift changes with clear indicators for unviewed items
2. **Notifications**: Use the unviewed count for notification badges
3. **Mark as Viewed**: Allow employees to mark changes as viewed
4. **Summary Dashboard**: Show summary statistics and recent changes

### Key UI Considerations:
- **Visual indicators** for unviewed changes (badges, highlighting)
- **Clear change type icons** and descriptions
- **Before/after comparison** for schedule changes
- **Effective date prominence** so employees know when changes take effect
- **Owner attribution** so employees know who made the change

---

## Migration from Old System

If you had any existing shift request functionality that allowed employees to request changes:

1. **Remove employee request endpoints** - employees can no longer create requests
2. **Update frontend** - remove request creation UI for employees
3. **Add owner creation UI** - build admin interface for creating shift changes
4. **Data migration** - if you have existing requests, you may want to migrate approved ones to the new system

The new system is completely owner-driven, eliminating the request/approval workflow in favor of direct owner control. 