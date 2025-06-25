# 🤖 Vapi AI Agent Endpoint Reference

## 🚀 **Webhook Configuration**

**Vapi Webhook URL**: `https://employee-management-backend-507748767742.us-central1.run.app/api/vapi-webhook`

**Required Headers**:
- `x-vapi-secret`: Your secret token
- `Content-Type`: application/json

---

## 📋 **Available Endpoints for Vapi**

### **✅ RECOMMENDED - Fast & Reliable Endpoints**

#### 1. **Employee Details (Individual)**
```
/admin/analytics/employee/{employee_id}/details
```
- **Performance**: Fast (~500ms)
- **Use Case**: Get detailed info about one employee
- **Returns**: Recent clocks, weekly hours, pay calculations

#### 2. **Labor Preview (Dealership)**
```
/admin/analytics/dealership/{dealership_id}/labor-preview
```
- **Performance**: Very Fast (~200ms)
- **Use Case**: Quick dealership status check
- **Returns**: Today's costs, active employees, burn rate

#### 3. **Active Employees (Dealership)**
```
/admin/analytics/active/dealership/{dealership_id}
```
- **Performance**: Fast (~300ms)
- **Use Case**: See who's currently working
- **Returns**: Real-time active employee list

#### 4. **Employee Hours Breakdown**
```
/admin/analytics/dealership/{dealership_id}/employee-hours
```
- **Performance**: Fast (~400ms)
- **Use Case**: Payroll and hours analysis
- **Returns**: Regular/overtime hours for each employee

---

### **⚠️ SLOW ENDPOINTS - Use with Caution**

#### 1. **Comprehensive Labor Spend**
```
/admin/analytics/dealership/{dealership_id}/comprehensive-labor-spend
```
- **Performance**: VERY SLOW (~2+ minutes)
- **Issue**: Fetches ALL employees from Firestore + complex calculations
- **Recommendation**: Only use for detailed management reports
- **Alternative**: Use "Labor Preview" for most cases

#### 2. **All Employee Details**
```
/admin/analytics/employees/details
```
- **Performance**: SLOW (~30+ seconds)
- **Issue**: Processes every employee in the system
- **Recommendation**: Use pagination or filter by dealership

---

## 🎯 **Vapi Function Call Examples**

### **Example 1: Get Employee Details**
```json
{
  "type": "function-call",
  "functionCall": {
    "name": "getCompanyData",
    "parameters": {
      "endpoint_path": "/admin/analytics/employee/{employee_id}/details",
      "path_params": {
        "employee_id": "yPkVsJnqIJWrHIqgDQSUaHKdUhJ2"
      }
    }
  }
}
```

### **Example 2: Get Dealership Labor Status**
```json
{
  "type": "function-call", 
  "functionCall": {
    "name": "getCompanyData",
    "parameters": {
      "endpoint_path": "/admin/analytics/dealership/{dealership_id}/labor-preview",
      "path_params": {
        "dealership_id": "dealership123"
      }
    }
  }
}
```

### **Example 3: Get Active Employees**
```json
{
  "type": "function-call",
  "functionCall": {
    "name": "getCompanyData", 
    "parameters": {
      "endpoint_path": "/admin/analytics/active/dealership/{dealership_id}",
      "path_params": {
        "dealership_id": "dealership123"
      }
    }
  }
}
```

---

## 🚨 **Common Issues & Solutions**

### **Issue: 404 Not Found**
**Cause**: Using `/api/` prefix in endpoint_path
**Solution**: Remove `/api/` from the beginning of paths
- ❌ Wrong: `/api/admin/analytics/employee/123/details`
- ✅ Correct: `/admin/analytics/employee/123/details`

### **Issue: Request Timeout**
**Cause**: Using slow endpoints like comprehensive-labor-spend
**Solutions**:
1. Use faster alternatives (labor-preview instead of comprehensive)
2. Increase Vapi timeout settings
3. Implement caching on backend

### **Issue: 401 Unauthorized**
**Cause**: Missing or incorrect VAPI_SECRET_TOKEN
**Solution**: Ensure environment variable is set in Cloud Run deployment

---

## ⚡ **Performance Optimization Tips**

### **For Vapi Conversations**
1. **Use Labor Preview** for quick status checks
2. **Use specific employee endpoints** instead of bulk endpoints
3. **Cache frequent requests** in your Vapi logic
4. **Implement fallbacks** for slow endpoints

### **Recommended Response Times**
- **Labor Preview**: ~200ms (Perfect for real-time)
- **Employee Details**: ~500ms (Good for conversations)
- **Employee Hours**: ~400ms (Good for analysis)
- **Comprehensive**: 2+ minutes (Only for reports)

---

## 🔄 **Webhook Response Format**

All successful responses return:
```json
{
  "tool_results": [
    {
      "tool_call_id": "call_123", 
      "result": {
        // The actual API response data
      }
    }
  ]
}
```

---

## 📊 **Recommended Endpoint Strategy**

### **For Real-time Queries** (Most Vapi conversations)
- Use `/admin/analytics/dealership/{id}/labor-preview`
- Use `/admin/analytics/active/dealership/{id}`
- Use `/admin/analytics/employee/{id}/details`

### **For Detailed Analysis** (Management requests)
- Use `/admin/analytics/dealership/{id}/employee-hours`
- Only use comprehensive endpoints when specifically needed

### **For Emergency/Fallback**
- Always have labor-preview as a backup
- Implement timeout handling in Vapi functions 