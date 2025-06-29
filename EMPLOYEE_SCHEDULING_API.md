# 🗓️ Employee Scheduling API Documentation

## Overview
A comprehensive employee scheduling system with drag-and-drop functionality, overtime prevention, and cost optimization recommendations.

## 🚀 Quick Setup

### 1. Create Database Table
```bash
python scripts/create_employee_scheduling_table.py
```

### 2. Available Endpoints
All endpoints are prefixed with `/admin/scheduling/` and require admin authentication.

---

## 📋 API Endpoints

### 👥 Get Schedulable Employees
```http
GET /admin/scheduling/employees?target_date=2025-01-17
```

**Response:**
```json
[
  {
    "id": "employee_123",
    "name": "John Doe",
    "role": "employee",
    "current_dealership": "toyota_main",
    "weekly_hours": 32.5,
    "is_overtime": false,
    "hourly_wage": 18.50,
    "availability_notes": "Available weekends"
  }
]
```

**Use Case:** Populate the left sidebar with draggable employee cards sorted by weekly hours (lowest first for cost optimization).

---

### 🏢 Get Schedulable Dealerships
```http
GET /admin/scheduling/dealerships?target_date=2025-01-17
```

**Response:**
```json
[
  {
    "id": "toyota_main", 
    "name": "Toyota Main",
    "current_employees": 3,
    "scheduled_employees": 5
  }
]
```

**Use Case:** Create drop zones for each dealership showing current vs. scheduled employee counts.

---

### ➕ Create Scheduled Shift (Drag & Drop)
```http
POST /admin/scheduling/shifts
```

**Request Body:**
```json
{
  "employee_id": "employee_123",
  "dealership_id": "toyota_main",
  "shift_date": "2025-01-17",
  "start_time": "09:00:00",
  "end_time": "17:00:00",
  "break_minutes": 30,
  "notes": "Morning shift supervisor",
  "special_instructions": "Handle customer escalations"
}
```

**Response:**
```json
{
  "id": 1,
  "employee_id": "employee_123",
  "employee_name": "John Doe",
  "dealership_id": "toyota_main", 
  "dealership_name": "Toyota Main",
  "shift_date": "2025-01-17",
  "start_time": "09:00:00",
  "end_time": "17:00:00",
  "estimated_hours": 7.5,
  "break_minutes": 30,
  "status": "scheduled",
  "is_overtime_shift": false,
  "weekly_hours_before_shift": 32.5,
  "created_at": "2025-01-17T10:30:00Z"
}
```

**Use Case:** When user drops an employee card onto a dealership, create the shift with time picker modal.

---

### 📅 Get Scheduled Shifts
```http
GET /admin/scheduling/shifts?start_date=2025-01-17&end_date=2025-01-23&dealership_id=toyota_main
```

**Query Parameters:**
- `start_date` (optional): Filter shifts from this date
- `end_date` (optional): Filter shifts until this date  
- `employee_id` (optional): Filter by specific employee
- `dealership_id` (optional): Filter by specific dealership
- `status` (optional): Filter by status (scheduled, confirmed, cancelled, completed)

**Use Case:** Load existing shifts to populate the scheduling board on initial load or date change.

---

### ✏️ Update Scheduled Shift
```http
PUT /admin/scheduling/shifts/1
```

**Request Body:** (all fields optional)
```json
{
  "dealership_id": "ford_main",
  "start_time": "10:00:00", 
  "end_time": "18:00:00",
  "status": "confirmed",
  "notes": "Updated shift timing"
}
```

**Use Case:** When user drags shift to different dealership or edits shift details in modal.

---

### 🗑️ Delete Scheduled Shift
```http
DELETE /admin/scheduling/shifts/1
```

**Use Case:** Remove shift when user drags it to trash or cancels it.

---

### 💡 Get Employee Recommendations
```http
GET /admin/scheduling/recommendations?target_date=2025-01-17&max_recommendations=10
```

**Response:**
```json
[
  {
    "employee_id": "employee_456",
    "employee_name": "Jane Smith", 
    "current_weekly_hours": 18.5,
    "hours_until_overtime": 21.5,
    "recommended_shifts": 2,
    "cost_efficiency_score": 85.2,
    "availability_score": 92.0,
    "reason": "Low hours (18.5/week) - high availability"
  }
]
```

**Use Case:** Show smart recommendations panel highlighting cost-effective employees to schedule.

---

### 📊 Get Scheduling Dashboard
```http
GET /admin/scheduling/dashboard?target_date=2025-01-17
```

**Response:**
```json
{
  "date": "2025-01-17",
  "total_scheduled_hours": 156.5,
  "total_estimated_cost": 2847.50,
  "employees_in_overtime": 3,
  "understaffed_dealerships": ["ford_main"],
  "overstaffed_dealerships": ["toyota_north"],
  "recommendations": [...]
}
```

**Use Case:** Display overview metrics and alerts at the top of scheduling interface.

---

## 🎨 Frontend Implementation Guide

### Trello-Style Board Structure
```
┌─────────────────┬─────────────────────────────────────────┐
│  EMPLOYEES      │            DEALERSHIPS                  │
│  (Draggable)    │              (Drop Zones)               │
├─────────────────┼─────────────────────────────────────────┤
│ 👤 John Doe     │  🏢 Toyota Main        🏢 Ford Main    │
│    32.5h/week   │     ┌─────────────┐    ┌─────────────┐  │
│    $18.50/hr    │     │ 9AM-5PM     │    │ 10AM-6PM    │  │
│                 │     │ Jane Smith  │    │ Bob Wilson  │  │
│ 👤 Jane Smith   │     └─────────────┘    └─────────────┘  │
│    18.5h/week   │                                         │
│    $16.00/hr    │  🏢 Honda Central     🏢 Nissan East   │
│    ⭐ Recommended│     ┌─────────────┐    ┌─────────────┐  │
│                 │     │    Empty    │    │ 8AM-4PM     │  │
│ 👤 Bob Wilson   │     │             │    │ John Doe    │  │
│    45.2h/week   │     └─────────────┘    └─────────────┘  │
│    ⚠️ Overtime   │                                         │
└─────────────────┴─────────────────────────────────────────┘
```

### Key Features to Implement

#### 1. **Drag & Drop Logic**
```javascript
// When employee is dropped on dealership
const handleEmployeeDrop = async (employeeId, dealershipId) => {
  // Show time picker modal
  const shiftDetails = await showTimePickerModal();
  
  // Create shift via API
  const response = await fetch('/admin/scheduling/shifts', {
    method: 'POST',
    body: JSON.stringify({
      employee_id: employeeId,
      dealership_id: dealershipId,
      shift_date: selectedDate,
      ...shiftDetails
    })
  });
  
  // Update UI with new shift
  if (response.ok) {
    const shift = await response.json();
    addShiftToBoard(shift);
  }
};
```

#### 2. **Smart Visual Indicators**
- 🟢 **Green employees**: < 35 hours/week (cost-effective)
- 🟡 **Yellow employees**: 35-40 hours/week (moderate)  
- 🔴 **Red employees**: > 40 hours/week (overtime risk)
- ⭐ **Star badge**: Recommended employees
- 💰 **Cost display**: Show hourly wage on employee cards

#### 3. **Real-time Calculations**
```javascript
// Update employee hours when shift is added/removed
const updateEmployeeHours = (employeeId, hoursChange) => {
  const employee = employees.find(e => e.id === employeeId);
  employee.weekly_hours += hoursChange;
  employee.is_overtime = employee.weekly_hours > 40;
  
  // Update visual indicators
  updateEmployeeCardStyle(employee);
};
```

#### 4. **Time Picker Modal**
```javascript
const TimePickerModal = ({ onConfirm, onCancel }) => {
  const [startTime, setStartTime] = useState('09:00');
  const [endTime, setEndTime] = useState('17:00');
  const [breakMinutes, setBreakMinutes] = useState(30);
  
  const estimatedHours = calculateHours(startTime, endTime, breakMinutes);
  
  return (
    <Modal>
      <h3>Schedule Shift</h3>
      <TimeInput label="Start Time" value={startTime} onChange={setStartTime} />
      <TimeInput label="End Time" value={endTime} onChange={setEndTime} />
      <NumberInput label="Break (minutes)" value={breakMinutes} onChange={setBreakMinutes} />
      <p>Estimated Hours: {estimatedHours}</p>
      <Button onClick={() => onConfirm({startTime, endTime, breakMinutes})}>Confirm</Button>
      <Button onClick={onCancel}>Cancel</Button>
    </Modal>
  );
};
```

#### 5. **Recommendations Panel**
```javascript
const RecommendationsPanel = ({ recommendations }) => (
  <div className="recommendations-panel">
    <h3>💡 Smart Recommendations</h3>
    {recommendations.map(rec => (
      <div key={rec.employee_id} className="recommendation-card">
        <span className="employee-name">{rec.employee_name}</span>
        <span className="hours">{rec.current_weekly_hours}h/week</span>
        <span className="efficiency">⭐ {rec.cost_efficiency_score}% efficient</span>
        <span className="reason">{rec.reason}</span>
      </div>
    ))}
  </div>
);
```

---

## 🔧 Advanced Features

### Shift Status Management
- **Scheduled** (blue): Initial state when shift is created
- **Confirmed** (green): Employee/manager confirmed availability  
- **Cancelled** (red): Shift was cancelled
- **Completed** (gray): Shift is finished

### Overtime Prevention Alerts
```javascript
const checkOvertimeAlert = (employee, additionalHours) => {
  const newTotal = employee.weekly_hours + additionalHours;
  if (newTotal > 40) {
    return {
      type: 'warning',
      message: `This will put ${employee.name} into overtime (${newTotal}h/week)`
    };
  }
  return null;
};
```

### Cost Optimization Features
- Sort employees by cost-efficiency score
- Highlight recommended employees with star badges
- Show real-time cost calculations
- Alert when shifts exceed budget thresholds

---

## 🚀 Getting Started

1. **Run the migration**: `python scripts/create_employee_scheduling_table.py`
2. **Start your FastAPI server**: The endpoints will be available at `/admin/scheduling/`
3. **Build your frontend**: Use the drag-and-drop examples above
4. **Test with Postman**: Try the endpoints to understand the data flow

Your Trello-style employee scheduling system is ready to go! 🎉 