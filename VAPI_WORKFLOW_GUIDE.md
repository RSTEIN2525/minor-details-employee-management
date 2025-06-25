# 🚀 VAPI Workflow System Guide

## 🎯 **Overview**

The new VAPI webhook system uses **intelligent workflows** with **AI-powered name matching** instead of rigid endpoint mapping. This makes voice interactions much more natural and user-friendly.

---

## 🧠 **How It Works**

1. **User speaks**: "Get me details for John Smith" or "What's the status at Toyota dealership?"
2. **VAPI sends workflow**: Contains the action type and raw user speech
3. **Backend processes**:
   - Loads cached employee/dealership data
   - Uses OpenAI GPT-3.5-turbo to find best match
   - Calls the appropriate function
   - Returns structured results

---

## 📋 **Available Workflows**

### Employee Information
- **Action**: `get_employee_details`
- **Example User Input**: "John Smith", "Get details for Sarah"
- **What it does**: Finds matching employee and returns detailed analytics

### Dealership Status
- **Action**: `get_dealership_status`  
- **Example User Input**: "Toyota dealership", "Status for Honda location"
- **What it does**: Returns labor preview and current status

### Active Employees at Dealership
- **Action**: `get_dealership_active_employees`
- **Example User Input**: "Who's working at Ford?", "Active employees Toyota"
- **What it does**: Shows currently clocked-in employees

### Company Overview
- **Action**: `get_company_overview`
- **Example User Input**: "Company status", "Today's summary"
- **What it does**: Returns company-wide financial summary

### All Active Employees
- **Action**: `get_all_active_employees`
- **Example User Input**: "Who's working right now?", "All active employees"
- **What it does**: Shows all active employees across all locations

---

## 🔧 **VAPI Integration**

### Webhook Payload Format
```json
{
  "type": "workflow",
  "workflow": {
    "action": "get_employee_details",
    "user_input": "John Smith",
    "token": "your_auth_token"
  }
}
```

### Response Format
```json
{
  "result": {
    "success": true,
    "data": { /* actual endpoint response */ },
    "message": "Retrieved details for John Smith"
  }
}
```

---

## 🧠 **Smart Matching**

The system uses OpenAI GPT-3.5-turbo to handle:
- **Partial names**: "John" → "John Smith"
- **Abbreviations**: "Toyota" → "Toyota of Downtown"
- **Phonetic similarities**: "Sara" → "Sarah"
- **Common variations**: "Ford dealership" → "Ford Location 1"

---

## ⚡ **Performance Features**

- **Caching**: Employee/dealership data cached for 1 hour
- **Direct function calls**: No HTTP self-requests (eliminates deadlocks)
- **Fast LLM**: GPT-3.5-turbo with minimal tokens for speed
- **Error handling**: Graceful fallbacks and helpful error messages

---

## 🔒 **Security**

- VAPI secret token validation
- Admin role verification for all operations
- Token passed directly from VAPI (no Firebase fetch needed)

---

## 🚀 **Deployment Requirements**

### Environment Variables
```bash
VAPI_SECRET_TOKEN=your_vapi_secret
OPENAI_API_KEY=your_openai_key
```

### Dependencies Added
- `openai==0.28.1` (for LLM matching)

---

## 🛠️ **Development Notes**

- **Cache TTL**: 3600 seconds (1 hour) - adjustable
- **LLM Model**: GPT-3.5-turbo (cheap and fast)
- **Max tokens**: 50 (for quick ID responses)
- **Temperature**: 0.1 (deterministic matching)

---

## 🔍 **Debugging**

Check logs for:
- Cache refresh events
- LLM matching results
- Workflow execution details
- Error handling

Example log output:
```
INFO:api.vapi_handler:Refreshing employee cache...
INFO:api.vapi_handler:Cached 45 employees
INFO:api.vapi_handler:LLM match result for 'John Smith': emp_12345
INFO:api.vapi_handler:Processing workflow: get_employee_details with input: 'John Smith'
```

---

## 🎯 **Next Steps**

1. Add more workflow types as needed
2. Implement batch operations for multiple queries
3. Add conversation context for multi-turn interactions
4. Optimize caching strategy based on usage patterns 