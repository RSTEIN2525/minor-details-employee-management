# Executive API Reference
## Complete Admin/Owner Endpoints for Company Operations

This document provides a comprehensive overview of all administrative endpoints available to executives and owners. These APIs provide real-time visibility into labor costs, employee productivity, operational efficiency, and compliance across all dealership locations.

---

## 💰 **Revenue & Profit Analytics (NEW!)**

### Company-Wide Financial Performance

#### **GET /admin/financial/company-summary/today**
**Purpose**: Complete financial overview of the entire company for today
- **Business Value**: Instant visibility into total revenue, profit/loss, and performance metrics
- **Returns**: 
  - Total revenue across all dealerships (tickets + washes + photos + lot prep)
  - Total labor costs and profit/loss calculation
  - Revenue breakdown by service type
  - Count of profitable vs unprofitable dealerships
  - Service volume metrics (total tickets, washes, photos, lot prep)
- **Use Case**: Daily executive briefing, board reporting, performance monitoring

#### **GET /admin/financial/revenue-only/company-total/today**
**Purpose**: Quick company revenue total for today
- **Business Value**: Fast revenue check for daily targets
- **Returns**: Total company revenue and timestamp
- **Use Case**: Quick revenue status check, daily goal tracking

#### **GET /admin/financial/profit-only/company-total/today**
**Purpose**: Quick company profit/loss for today
- **Business Value**: Immediate profitability status
- **Returns**: Total profit/loss, revenue, labor costs, and profitability status
- **Use Case**: Daily profit monitoring, performance alerts

### Individual Dealership Analytics

#### **GET /admin/financial/dealership/{dealership_id}/summary**
**Purpose**: Complete financial summary for a specific dealership
- **Business Value**: Detailed performance analysis for individual locations
- **Returns**: 
  - Revenue breakdown (tickets, washes, photos, lot prep)
  - Service volume counts
  - Labor costs and profit/loss
  - Labor percentage of revenue
- **Use Case**: Dealership performance reviews, location comparison

#### **GET /admin/financial/dealership/{dealership_id}/detailed-breakdown**
**Purpose**: Service-by-service breakdown for a dealership
- **Business Value**: Granular analysis of service performance
- **Returns**: 
  - Individual ticket services breakdown
  - Wash, photo, and lot prep details
  - Profit analysis by service type
- **Use Case**: Service optimization, pricing analysis

#### **GET /admin/financial/all-dealerships/summary**
**Purpose**: Financial summary for all dealerships (ranked by performance)
- **Business Value**: Compare all locations side-by-side
- **Returns**: All dealership summaries sorted by revenue
- **Use Case**: Performance rankings, resource allocation decisions

### Date Range & Historical Analysis

#### **GET /admin/financial/date-range/summary**
**Purpose**: Financial performance over a custom date range
- **Business Value**: Trend analysis and historical performance tracking
- **Parameters**: start_date, end_date (up to 90 days)
- **Returns**: 
  - Total revenue, labor costs, profit for the range
  - Daily averages
  - Dealership performance over the period
- **Use Case**: Monthly/quarterly reporting, trend analysis

#### **GET /admin/financial/top-performers/today**
**Purpose**: Top performing dealerships by different metrics
- **Business Value**: Identify best performers and success patterns
- **Returns**: 
  - Top dealerships by revenue
  - Top dealerships by profit
  - Top dealerships by service volume
- **Use Case**: Performance recognition, best practice identification

---

## 🏢 **Company-Wide Financial Analytics**

### Real-Time Labor Cost Monitoring

#### **GET /admin/analytics/all-dealerships/labor-costs-today**
**Purpose**: Get today's total labor costs across ALL dealerships
- **Business Value**: Instant visibility into daily labor spend company-wide
- **Returns**: 
  - Total company labor cost for today
  - Breakdown by dealership
  - Analysis timestamp for data freshness
- **Use Case**: Morning executive dashboard, real-time cost monitoring

#### **GET /admin/analytics/labor/daily/enhanced**
**Purpose**: Detailed daily labor analysis with enhanced breakdowns
- **Business Value**: Deep dive into daily labor efficiency by location and time
- **Returns**: 
  - Total labor spend and hours worked
  - Dealership breakdown with employee counts
  - Hourly breakdown showing peak labor times
  - Dealership names for easy identification
- **Use Case**: Daily operations review, identifying peak productivity hours

#### **GET /admin/analytics/labor/weekly**
**Purpose**: Weekly labor spend trends across dealerships
- **Business Value**: Track labor cost trends and seasonal patterns
- **Returns**: Weekly labor spend by dealership with date ranges
- **Use Case**: Weekly executive reviews, budget planning

---

## 🏪 **Dealership-Specific Operations**

### Labor Cost & Employee Activity

#### **GET /admin/analytics/dealership/{dealership_id}/comprehensive-labor-spend**
**Purpose**: Complete labor analysis for a specific dealership
- **Business Value**: Full operational picture of dealership performance
- **Returns**: 
  - **Summary**: Employee counts, today's costs, overtime breakdown
  - **Individual Employees**: Detailed breakdown per employee including:
    - Current active status and shift duration
    - Today's work hours (regular vs overtime)
    - Today's labor costs and vacation costs
    - Weekly hours and cost totals
  - **Top Performers**: Highest earners and most hours worked today
- **Use Case**: Dealership performance reviews, identifying top performers

#### **GET /admin/analytics/dealership/{dealership_id}/labor-preview**
**Purpose**: Quick snapshot of current dealership labor costs
- **Business Value**: Fast operational status check
- **Returns**: 
  - Real-time labor costs and hours today
  - Currently active employees
  - Projected daily costs based on current burn rate
- **Use Case**: Quick status checks, real-time monitoring

#### **GET /admin/analytics/active/dealership/{dealership_id}**
**Purpose**: Currently active employees at a specific dealership
- **Business Value**: Real-time workforce visibility
- **Returns**: 
  - List of active employees with shift details
  - Current hourly labor rate
  - Today's total labor spend
- **Use Case**: Real-time workforce management, shift monitoring

#### **GET /admin/analytics/dealership/{dealership_id}/employee-hours**
**Purpose**: Employee hours breakdown for date range
- **Business Value**: Detailed productivity and cost analysis
- **Returns**: 
  - Each employee's total, regular, and overtime hours
  - Estimated pay calculations
  - Currently active status
  - Summary totals for the dealership
- **Use Case**: Payroll preparation, productivity analysis

### All Active Employees Company-Wide

#### **GET /admin/analytics/active/all**
**Purpose**: See all active employees across ALL dealerships
- **Business Value**: Company-wide real-time workforce visibility
- **Returns**: Active employees grouped by dealership with real-time status
- **Use Case**: Operations center monitoring, company-wide status

---

## 👥 **Employee Management & Analytics**

### Individual Employee Insights

#### **GET /admin/analytics/employee/{employee_id}/details**
**Purpose**: Complete employee performance and financial overview
- **Business Value**: Individual employee productivity and cost analysis
- **Returns**: 
  - **Recent Activity**: Last 20 clock entries
  - **Weekly Summaries**: 4 weeks of work history with pay breakdown
  - **Today's Summary**: Current day performance and status
  - **Financial**: Two-week total pay calculation
- **Use Case**: Employee reviews, performance analysis, payroll verification

#### **GET /admin/analytics/employees/details**
**Purpose**: Bulk employee details for all employees (with pagination)
- **Business Value**: Company-wide employee performance overview
- **Returns**: Same detailed breakdown as individual endpoint but for multiple employees
- **Use Case**: Payroll processing, company-wide performance reviews

### Employee Administrative Actions

#### **GET /admin/user-requests/users**
**Purpose**: List all employees in the system
- **Business Value**: Employee directory for administrative actions
- **Returns**: Employee IDs and display names
- **Use Case**: User management, directory lookup

#### **GET /admin/user-requests/users/wages**
**Purpose**: Complete wage overview for all employees
- **Business Value**: Payroll oversight and wage management
- **Returns**: All employees with their current hourly wages
- **Use Case**: Wage audits, payroll management

#### **PUT /admin/user-requests/users/{user_id}/wage**
**Purpose**: Update employee hourly wage
- **Business Value**: Direct wage management capability
- **Use Case**: Raises, wage adjustments, new hire setup

---

## ⏰ **Time Management & Attendance**

### Direct Time Manipulation

#### **POST /admin/time/direct-single-clock-creation**
**Purpose**: Create individual clock-in or clock-out entries
- **Business Value**: Correct missing punches, handle special situations
- **Parameters**: Employee, date, time, punch type (IN/OUT), location, reason
- **Use Case**: Fixing missed punches, emergency time entry

#### **POST /admin/time/direct-single-clock-edit**
**Purpose**: Edit existing clock punch times
- **Business Value**: Correct timing errors, adjust for legitimate reasons
- **Use Case**: Time corrections, dispute resolution

#### **POST /admin/time/direct-single-clock-delete**
**Purpose**: Remove erroneous clock entries
- **Business Value**: Clean up data errors, handle duplicate punches
- **Use Case**: Error correction, data cleanup

#### **POST /admin/time/direct-change-punch-dealership**
**Purpose**: Move a punch from one dealership to another
- **Business Value**: Correct location errors, handle employee transfers
- **Use Case**: Location corrections, multi-site employee management

### Time History & Audit Trail

#### **GET /admin/time/employee/{employee_id}/recent-punches**
**Purpose**: Recent punch history for specific employee
- **Business Value**: Quick employee activity review
- **Returns**: Last 20 clock entries with timestamps and locations
- **Use Case**: Employee attendance review, troubleshooting

#### **GET /admin/time/recent-entries**
**Purpose**: Recent time entries across all employees
- **Business Value**: Company-wide activity monitoring
- **Returns**: Latest 50 clock entries system-wide
- **Use Case**: Activity monitoring, system health check

#### **GET /admin/time/employee/{employee_id}/changes**
**Purpose**: Admin-made changes to employee's time records
- **Business Value**: Audit trail for time modifications
- **Returns**: History of all admin adjustments with reasons
- **Use Case**: Audit compliance, change tracking

### Clock Request Management

#### **GET /admin/clock-requests/all**
**Purpose**: Review employee requests for time changes
- **Business Value**: Manage employee-initiated time correction requests
- **Returns**: All pending/processed time change requests
- **Use Case**: Approval workflow, employee request management

#### **POST /admin/clock-requests/{request_id}/approve**
**Purpose**: Approve employee time change requests
- **Business Value**: Streamlined approval process for legitimate requests
- **Use Case**: Request approval workflow

#### **POST /admin/clock-requests/{request_id}/deny**
**Purpose**: Reject employee time change requests
- **Business Value**: Control over time modifications, maintain data integrity
- **Use Case**: Request rejection with documentation

---

## 🏖️ **Vacation & Time Off Management**

### Vacation Administration

#### **POST /admin/vacation/grant-vacation**
**Purpose**: Grant vacation time to employees
- **Business Value**: Direct vacation time management
- **Parameters**: Employee, date, hours, vacation type, notes
- **Use Case**: Vacation approvals, time off management

#### **GET /admin/vacation/vacation-entries**
**Purpose**: View all vacation entries with filtering options
- **Business Value**: Complete vacation oversight and cost tracking
- **Returns**: 
  - Total vacation hours and cost calculations
  - Filterable by employee, dealership, date range
  - Complete vacation history
- **Use Case**: Vacation policy oversight, cost analysis

#### **GET /admin/vacation/employee/{employee_id}/vacation**
**Purpose**: Individual employee vacation history
- **Business Value**: Employee-specific vacation tracking
- **Returns**: All vacation entries for specific employee with pay calculations
- **Use Case**: Employee vacation reviews, policy compliance

#### **GET /admin/vacation/recent-activity**
**Purpose**: Combined recent activity (time changes + vacation)
- **Business Value**: Unified view of all administrative actions
- **Returns**: Recent admin actions across time and vacation systems
- **Use Case**: Administrative audit trail, activity monitoring

---

## 🏪 **Location & Shop Management**

### Shop Operations

#### **GET /admin/shop-requests/shops**
**Purpose**: List all business locations
- **Business Value**: Location management and oversight
- **Returns**: All shops with coordinates and geofence information
- **Use Case**: Location management, geofence setup

#### **POST /admin/shop-requests/shops**
**Purpose**: Create new business locations
- **Business Value**: Expansion support, new location setup
- **Use Case**: Opening new locations, business expansion

#### **PUT /admin/shop-requests/shops/{shop_id}**
**Purpose**: Update existing location details
- **Business Value**: Maintain accurate location data
- **Use Case**: Address changes, geofence adjustments

### Dealership Information

#### **GET /admin/dealership-requests/dealerships**
**Purpose**: List all dealership information
- **Business Value**: Dealership directory and management
- **Use Case**: Location lookup, administrative reference

---

## 📱 **Device & Security Management**

### Device Approval System

#### **GET /admin/device-requests/pending**
**Purpose**: Review pending device registration requests
- **Business Value**: Security control over employee device access
- **Returns**: Employees requesting device approval with photos
- **Use Case**: Security approval workflow

#### **POST /admin/device-requests/{request_id}/approve**
**Purpose**: Approve employee device registration
- **Business Value**: Grant secure access to employees
- **Use Case**: Device security management

#### **GET /admin/device-requests/approved**
**Purpose**: View recently approved devices
- **Business Value**: Track approved device access
- **Use Case**: Security audit, access management

#### **GET /admin/device-requests/users/{user_id}/devices**
**Purpose**: See all approved devices for specific employee
- **Business Value**: Individual device access oversight
- **Use Case**: Employee device management, security review

---

## 🚨 **Safety & Compliance**

### Injury Reporting

#### **GET /admin/injury/reports**
**Purpose**: Workplace injury reporting and statistics
- **Business Value**: Safety compliance and risk management
- **Returns**: 
  - Injury rates and statistics
  - Individual injury reports
  - Filterable by date, location, employee
- **Use Case**: Safety compliance, insurance reporting

#### **GET /admin/injury/employee/{employee_id}/reports**
**Purpose**: Individual employee injury history
- **Business Value**: Employee safety tracking
- **Use Case**: Individual safety reviews, incident tracking

#### **GET /admin/injury/dealership/{dealership_id}/summary**
**Purpose**: Dealership safety statistics
- **Business Value**: Location-specific safety performance
- **Returns**: Injury rates and trends for specific location
- **Use Case**: Location safety management, compliance reporting

---

## 🔧 **System Administration**

### Data Quality & Audit

All admin endpoints include comprehensive audit trails with:
- Admin user identification
- Timestamp tracking
- Reason documentation
- Original data preservation

### Authentication Requirements

All endpoints require:
- Valid Firebase authentication token
- Admin role ("owner") in user profile
- Proper authorization headers

---

## 📊 **Key Business Metrics Available**

### Financial Metrics
- **Revenue Tracking**: Real-time revenue from tickets, washes, photos, lot prep
- **Profit & Loss Analysis**: Complete P&L calculations with labor cost integration
- **Labor Cost Analysis**: Real-time labor costs (daily, weekly, by location)
- **Service Performance**: Revenue and volume by service type
- **Dealership Profitability**: Individual location profit/loss tracking
- **Overtime vs regular time breakdown**
- **Vacation cost tracking**
- **Payroll projections and burn rates**

### Operational Metrics
- Employee productivity by location and time
- Attendance patterns and trends
- Peak operational hours
- Resource allocation efficiency

### Compliance Metrics
- Injury reporting and safety statistics
- Time modification audit trails
- Device security and access control
- Vacation policy compliance

---

## 💡 **Executive Dashboard Recommendations**

### Daily Monitoring
1. **Company-wide labor costs** - Track daily spend
2. **Active employee status** - Real-time workforce visibility
3. **Pending requests** - Device approvals, time change requests
4. **Safety incidents** - Recent injury reports

### Weekly Reviews
1. **Labor cost trends** - Week-over-week analysis
2. **Employee productivity** - Top performers and locations
3. **Vacation utilization** - Time off patterns and costs
4. **Operational efficiency** - Peak hours and resource allocation

### Monthly Analysis
1. **Safety compliance** - Injury rates and trends
2. **Cost efficiency** - Labor cost per location analysis
3. **Employee patterns** - Attendance and productivity trends
4. **System health** - Audit trail reviews and data quality

This API suite provides complete operational visibility and control over your employee management system, enabling data-driven decisions and efficient business operations. 