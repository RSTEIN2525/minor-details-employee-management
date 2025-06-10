# Labor Analytics Endpoints Reference

## Overview
Two new powerful endpoints for tracking dealership labor costs and activity:

1. **Labor Preview** - Quick snapshot of today's spending (fast, lightweight)
2. **Comprehensive Labor Spend** - Complete analysis with all possible data (detailed, slower)

---

## 1. Quick Labor Preview Endpoint

### Endpoint
```
GET /admin/analytics/dealership/{dealership_id}/labor-preview
```

### Purpose
Get a quick snapshot of labor spending for TODAY at a specific dealership. Perfect for dashboards or status displays.

### What It Expects
- **Path Parameter**: `dealership_id` (string) - The dealership ID to analyze
- **Headers**: Authorization Bearer token (admin role required)

### What It Returns
```json
{
  "dealership_id": "dealership123",
  "current_time": "2024-01-15T14:30:00.000Z",
  
  // Today's spending so far
  "total_labor_cost_today": 1245.75,
  "total_work_cost_today": 1150.50,
  "total_vacation_cost_today": 95.25,
  
  // Hours so far today  
  "total_hours_today": 45.5,
  "total_work_hours_today": 42.0,
  "total_vacation_hours_today": 3.5,
  
  // Current activity
  "employees_currently_clocked_in": 5,
  "employees_who_worked_today": 8,
  "current_hourly_burn_rate": 125.00,
  
  // Quick stats
  "average_cost_per_employee_today": 155.72,
  "projected_daily_cost": 1500.00
}
```

### Key Metrics Explained
- `total_labor_cost_today`: Total money spent on labor today (work + vacation)
- `current_hourly_burn_rate`: Sum of hourly wages of all currently clocked-in employees
- `projected_daily_cost`: Estimated total daily cost based on current burn rate
- `employees_currently_clocked_in`: How many employees are actively working right now
- `employees_who_worked_today`: How many different employees clocked in at all today

### Frontend Usage Example
```javascript
// Fetch labor preview
async function getLaborPreview(dealershipId) {
  const response = await fetch(`/admin/analytics/dealership/${dealershipId}/labor-preview`, {
    headers: {
      'Authorization': `Bearer ${authToken}`,
      'Content-Type': 'application/json'
    }
  });
  
  const data = await response.json();
  
  // Update dashboard
  document.getElementById('total-cost').textContent = `$${data.total_labor_cost_today.toFixed(2)}`;
  document.getElementById('active-employees').textContent = data.employees_currently_clocked_in;
  document.getElementById('burn-rate').textContent = `$${data.current_hourly_burn_rate.toFixed(2)}/hr`;
  document.getElementById('projected-cost').textContent = `$${data.projected_daily_cost.toFixed(2)}`;
}

// Call every 5 minutes for live updates
setInterval(() => getLaborPreview('your-dealership-id'), 300000);
```

---

## 2. Comprehensive Labor Spend Endpoint

### Endpoint
```
GET /admin/analytics/dealership/{dealership_id}/comprehensive-labor-spend
```

### Purpose
Get EVERY possible piece of labor data for a dealership. This is the "kitchen sink" endpoint with complete employee breakdowns, detailed analytics, and insights.

### What It Expects
- **Path Parameter**: `dealership_id` (string) - The dealership ID to analyze
- **Headers**: Authorization Bearer token (admin role required)

### What It Returns
A large JSON object with three main sections:

#### Summary Object
```json
{
  "summary": {
    "dealership_id": "dealership123",
    "analysis_date": "2024-01-15",
    "analysis_timestamp": "2024-01-15T14:30:00.000Z",
    
    // Employee counts
    "total_employees": 15,
    "active_employees_today": 8,
    "employees_who_clocked_in_today": 8,
    "employees_currently_clocked_in": 5,
    
    // Today's labor costs
    "todays_total_work_hours": 42.0,
    "todays_total_vacation_hours": 3.5,
    "todays_total_combined_hours": 45.5,
    "todays_total_work_cost": 1150.50,
    "todays_total_vacation_cost": 95.25,
    "todays_total_labor_cost": 1245.75,
    
    // Time breakdown
    "todays_regular_hours": 40.0,
    "todays_overtime_hours": 2.0,
    "todays_regular_cost": 1050.00,
    "todays_overtime_cost": 100.50,
    
    // Current rates
    "current_hourly_labor_rate": 125.00,
    "average_hourly_wage": 22.50,
    "weighted_average_hourly_rate": 23.75,
    
    // Weekly aggregates
    "weekly_total_hours": 180.5,
    "weekly_regular_hours": 160.0,
    "weekly_overtime_hours": 20.5,
    "weekly_total_cost": 4250.00,
    
    // Clock activity
    "total_clock_ins_today": 8,
    "total_clock_outs_today": 3,
    
    // Efficiency metrics
    "cost_per_employee_today": 155.72,
    "hours_per_employee_today": 5.69
  }
}
```

#### Employee Details Array
```json
{
  "employees": [
    {
      "employee_id": "emp123",
      "employee_name": "John Smith",
      "hourly_wage": 25.00,
      
      // Current status
      "is_currently_active": true,
      "current_shift_start_time": "2024-01-15T08:00:00.000Z",
      "current_shift_duration_hours": 6.5,
      
      // Today's work
      "todays_total_hours": 6.5,
      "todays_regular_hours": 6.5,
      "todays_overtime_hours": 0.0,
      "todays_labor_cost": 162.50,
      "todays_vacation_hours": 0.0,
      "todays_vacation_cost": 0.0,
      "todays_total_cost": 162.50,
      
      // Weekly aggregates
      "weekly_total_hours": 32.5,
      "weekly_regular_hours": 32.5,
      "weekly_overtime_hours": 0.0,
      "weekly_labor_cost": 812.50,
      
      // Today's clock info
      "todays_clock_in_count": 1,
      "todays_first_clock_in": "2024-01-15T08:00:00.000Z",
      "todays_last_clock_out": null
    }
    // ... more employees
  ]
}
```

#### Top Performers
```json
{
  "top_earners_today": [
    // Top 5 employees by total cost today
  ],
  "most_hours_today": [
    // Top 5 employees by hours worked today
  ],
  "data_generated_at": "2024-01-15T14:30:00.000Z"
}
```

### Frontend Usage Example
```javascript
// Fetch comprehensive data
async function getComprehensiveLaborData(dealershipId) {
  const response = await fetch(`/admin/analytics/dealership/${dealershipId}/comprehensive-labor-spend`, {
    headers: {
      'Authorization': `Bearer ${authToken}`,
      'Content-Type': 'application/json'
    }
  });
  
  const data = await response.json();
  
  // Use summary for overview
  const summary = data.summary;
  updateOverviewDashboard(summary);
  
  // Use employee details for detailed tables
  populateEmployeeTable(data.employees);
  
  // Show top performers
  displayTopPerformers(data.top_earners_today, data.most_hours_today);
}

function updateOverviewDashboard(summary) {
  document.getElementById('total-employees').textContent = summary.total_employees;
  document.getElementById('active-now').textContent = summary.employees_currently_clocked_in;
  document.getElementById('total-cost').textContent = `$${summary.todays_total_labor_cost.toFixed(2)}`;
  document.getElementById('average-wage').textContent = `$${summary.average_hourly_wage.toFixed(2)}`;
  
  // Calculate efficiency metrics
  const efficiency = (summary.todays_total_combined_hours / summary.active_employees_today).toFixed(1);
  document.getElementById('efficiency').textContent = `${efficiency} hrs/employee`;
}

function populateEmployeeTable(employees) {
  const tableBody = document.getElementById('employee-table-body');
  tableBody.innerHTML = '';
  
  employees.forEach(emp => {
    const row = tableBody.insertRow();
    row.innerHTML = `
      <td>${emp.employee_name}</td>
      <td>${emp.is_currently_active ? '✅ Active' : '❌ Not Active'}</td>
      <td>${emp.todays_total_hours.toFixed(1)} hrs</td>
      <td>$${emp.todays_total_cost.toFixed(2)}</td>
      <td>$${emp.hourly_wage.toFixed(2)}/hr</td>
    `;
  });
}
```

---

## When to Use Which Endpoint

### Use Labor Preview When:
- Building dashboards that update frequently
- Showing quick status indicators
- Mobile apps or limited bandwidth
- Real-time monitoring displays
- You only need today's totals

### Use Comprehensive Labor Spend When:
- Building detailed analytics pages
- Generating management reports
- Analyzing individual employee performance
- Comparing current week vs today
- Need complete historical context
- Building employee management interfaces

---

## Error Handling

Both endpoints return standard HTTP status codes:

- `200` - Success
- `401` - Unauthorized (missing/invalid token)
- `403` - Forbidden (not admin role)
- `404` - Dealership not found
- `500` - Server error

Example error response:
```json
{
  "detail": "Dealership not found or access denied"
}
```

---

## Performance Notes

- **Labor Preview**: Fast (~200-500ms), lightweight response
- **Comprehensive**: Slower (~1-3 seconds), large response with all data
- Both endpoints are optimized with database indexes
- Consider caching comprehensive data for 5-10 minutes
- Preview data can be refreshed every 1-2 minutes

---

## Data Freshness

- All calculations are real-time based on current UTC time
- Vacation data is included automatically
- Overtime calculations use standard 40-hour weekly threshold
- Times are all returned in UTC with 'Z' suffix for consistency 