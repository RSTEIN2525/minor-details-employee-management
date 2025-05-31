# Migration Guide: From Employee Requests to Owner-Only Shift Changes

## Overview

This guide outlines the changes needed to migrate from the old employee-request system to the new owner-only shift change system.

## ✅ What's Been Added (Backend Complete)

### New Database Model
- `models/shift_change.py` - Complete shift change model with all necessary fields
- Auto-approved status for all owner-created changes
- Tracking of employee views and notifications

### New API Routes
- **Admin Routes** (`/admin/shift-changes/`):
  - `POST /create` - Create new shift changes (owner only)
  - `GET /all` - View all shift changes with filtering
  - `GET /employee/{id}` - View changes for specific employee
  - `GET /upcoming` - View upcoming changes
  - `DELETE /{id}` - Delete shift changes

- **User Routes** (`/shift-changes/`):
  - `GET /my-changes` - View own shift changes
  - `GET /upcoming` - View upcoming personal changes
  - `GET /unviewed` - View unviewed changes
  - `POST /{id}/mark-viewed` - Mark change as viewed
  - `POST /mark-all-viewed` - Mark all as viewed
  - `GET /summary` - Get summary dashboard data

### Database Integration
- Model automatically included in SQLModel table creation
- All imports added to `main.py`

## 🔄 What Needs to Be Changed (Frontend Tasks)

### 1. Remove Employee Request Functionality

**Current Employee Features to Remove:**
- Any UI that allows employees to request shift changes
- Request creation forms/modals
- "Request Change" buttons in employee dashboards
- Employee-facing request status tracking

**API Endpoints That May Need Removal:**
- Any employee-facing request creation endpoints
- Employee request status endpoints (if they exist)

### 2. Add Owner Dashboard Features

**New Owner UI Components Needed:**

#### A. Shift Change Creation Form
```typescript
interface CreateShiftChangeForm {
  employee_id: string;           // Dropdown of employees
  change_type: ShiftChangeType;  // Dropdown of change types
  effective_date: Date;          // Date picker
  reason: string;                // Text area
  notes?: string;                // Optional text area
  
  // Conditional fields based on change_type
  original_start_time?: string;  // Time picker
  original_end_time?: string;    // Time picker
  original_dealership_id?: string; // Dropdown
  
  new_start_time?: string;       // Time picker
  new_end_time?: string;         // Time picker
  new_dealership_id?: string;    // Dropdown
  
  swap_with_employee_id?: string; // Employee dropdown (for swaps)
}
```

#### B. Shift Change Management Dashboard
- **List View**: All shift changes with filtering by employee, date, type
- **Calendar View**: Visual representation of upcoming changes
- **Employee View**: Changes per employee
- **Quick Actions**: Edit, delete, create new changes

#### C. Upcoming Changes Widget
- Dashboard widget showing changes in next 7 days
- Notifications for changes taking effect soon

### 3. Update Employee Dashboard Features

**New Employee UI Components Needed:**

#### A. Shift Changes Notification System
- **Badge/Counter**: Show unviewed changes count
- **Notification Panel**: List of recent changes
- **Mark as Viewed**: Buttons to acknowledge changes

#### B. My Shift Changes Section
- **Timeline View**: Chronological list of all changes
- **Upcoming Changes**: Changes affecting upcoming shifts
- **Change Details**: Before/after comparison for schedule changes
- **Visual Indicators**: Unviewed changes highlighted

#### C. Summary Dashboard
- **Quick Stats**: Total changes, unviewed count, upcoming count
- **Recent Activity**: Last 5 changes with key details

## 📋 Implementation Checklist

### Backend (✅ Complete)
- [x] Create shift change model
- [x] Add admin API routes
- [x] Add user API routes  
- [x] Add database integration
- [x] Add comprehensive validation
- [x] Add user name enrichment
- [x] Test imports and basic functionality

### Frontend (🔄 To Do)

#### Owner Dashboard
- [ ] Remove any existing employee request approval UI
- [ ] Create shift change creation form with conditional fields
- [ ] Add shift change management dashboard
- [ ] Add employee-specific shift change views
- [ ] Add upcoming changes calendar/list view
- [ ] Add quick action buttons (edit, delete)
- [ ] Add filtering and search functionality

#### Employee Portal
- [ ] Remove shift change request creation UI
- [ ] Add "My Shift Changes" section
- [ ] Add notification badge for unviewed changes
- [ ] Add shift change timeline/history view
- [ ] Add mark-as-viewed functionality
- [ ] Add upcoming changes view
- [ ] Add summary dashboard widget

#### Shared Components
- [ ] Create shift change type icons/labels
- [ ] Create before/after comparison components
- [ ] Add date/time formatting utilities
- [ ] Create notification components

## 🎨 UI/UX Recommendations

### Owner Dashboard
1. **Creation Flow**: Multi-step form with change type selection first, then conditional fields
2. **Bulk Operations**: Allow creating multiple changes at once
3. **Templates**: Save common change patterns as templates
4. **Confirmation**: Clear confirmation before creating changes
5. **Audit Trail**: Show who created what and when

### Employee Portal
1. **Clear Notifications**: Prominent but not intrusive notification system
2. **Visual Hierarchy**: Unviewed changes should stand out
3. **Change Impact**: Clear before/after comparisons
4. **Effective Dates**: Prominent display of when changes take effect
5. **Mobile Friendly**: Ensure mobile employees can easily view changes

## 🔧 Technical Implementation Notes

### API Integration
```typescript
// Owner creating a shift change
const createShiftChange = async (changeData: CreateShiftChangeRequest) => {
  const response = await fetch('/admin/shift-changes/create', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(changeData)
  });
  return response.json();
};

// Employee viewing their changes
const getMyShiftChanges = async () => {
  const response = await fetch('/shift-changes/my-changes', {
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};

// Employee marking change as viewed
const markAsViewed = async (changeId: number) => {
  const response = await fetch(`/shift-changes/${changeId}/mark-viewed`, {
    method: 'POST',
    headers: { 'Authorization': `Bearer ${token}` }
  });
  return response.json();
};
```

### State Management
- **Owner State**: Track shift changes, employees, dealerships
- **Employee State**: Track personal changes, unviewed count, summary data
- **Real-time Updates**: Consider WebSocket or polling for live updates

### Error Handling
- **Validation Errors**: Clear field-level error messages
- **Permission Errors**: Graceful handling of unauthorized actions
- **Network Errors**: Retry mechanisms and offline indicators

## 🚀 Deployment Steps

1. **Database Migration**: The new table will be created automatically on next server start
2. **Backend Deployment**: Deploy the updated backend with new routes
3. **Frontend Updates**: Deploy frontend changes in phases:
   - Phase 1: Remove old employee request UI
   - Phase 2: Add basic owner creation functionality
   - Phase 3: Add advanced features and employee viewing
4. **User Training**: Train owners on the new shift change creation process
5. **Communication**: Inform employees about the new view-only system

## 📞 Support and Troubleshooting

### Common Issues
- **Permission Errors**: Ensure proper role checking in frontend
- **Time Format Errors**: Validate HH:MM format before sending to API
- **Employee Not Found**: Validate employee IDs before creating changes

### Testing Checklist
- [ ] Owner can create all types of shift changes
- [ ] Employees can view their changes
- [ ] Notification system works correctly
- [ ] Mark as viewed functionality works
- [ ] Filtering and pagination work
- [ ] Mobile responsiveness
- [ ] Error handling works properly

The new system provides much better control for owners while giving employees clear visibility into their shift changes! 