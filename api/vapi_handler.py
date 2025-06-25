import os
import logging
from typing import Optional, Dict, Any
import requests
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel
import json
from sqlmodel import Session

# Import the functions we want to call directly
# Financial Analytics
from api.admin_financial_routes import (
    get_company_financial_summary_today,
    get_company_revenue_total_today,
    get_company_profit_total_today,
    get_dealership_financial_summary,
    get_dealership_detailed_breakdown,
    get_all_dealerships_financial_summary,
    get_date_range_financial_summary,
    get_top_performers_today
)

# Labor Analytics  
from api.admin_analytics_routes import (
    get_all_active_employees,
    get_employee_details,
    get_all_employees_details,
    get_enhanced_daily_labor_spend,
    get_weekly_labor_spend,
    get_comprehensive_labor_spend,
    get_labor_preview,
    get_active_employees_by_dealership,
    get_dealership_employee_hours_breakdown,
    get_all_dealerships_labor_costs_today
)

# User Management
from api.admin_user_routes import (
    list_all_users_for_admin,
    list_all_user_wages_for_admin,
    set_or_update_user_wage,
    get_user_wage
)

# Time Management
from api.admin_time_routes import (
    get_employee_recent_punches,
    get_recent_global_entries,
    get_employee_admin_changes,
    admin_direct_single_clock_creation,
    admin_direct_single_clock_edit,
    admin_direct_single_clock_delete,
    admin_direct_change_punch_dealership
)

# Vacation Management
from api.admin_vacation_routes import (
    grant_vacation_time,
    get_vacation_entries,
    get_employee_vacation_entries,
    get_recent_combined_activity,
    get_vacation_types
)

# Clock Request Management
from api.admin_clock_request_routes import (
    get_all_clock_requests,
    approve_clock_request,
    deny_clock_request
)

from core.deps import get_session, require_admin_role_from_token
from utils.datetime_helpers import format_utc_datetime

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

# Environment variables
VAPI_SECRET_TOKEN = os.getenv("VAPI_SECRET_TOKEN")
INTERNAL_API_BASE_URL = os.getenv("INTERNAL_API_BASE_URL", "http://127.0.0.1:8000/api")
VAPI_TOKEN_URL = os.getenv("VAPI_TOKEN_URL", "https://get-vapi-token-507748767742.us-east4.run.app")

# Pydantic models for request validation
class FunctionParameters(BaseModel):
    endpoint_path: str
    path_params: Optional[Dict[str, Any]] = None
    query_params: Optional[Dict[str, Any]] = None

class FunctionCall(BaseModel):
    tool_call_id: Optional[str] = None  # Capture the ID if Vapi sends it
    name: str
    parameters: FunctionParameters

class VapiWebhook(BaseModel):
    type: str
    functionCall: Optional[FunctionCall] = None

# Response model for tool results
class ToolResult(BaseModel):
    tool_call_id: Optional[str] = None
    result: Any

class VapiResponse(BaseModel):
    tool_results: list[ToolResult]

# --- Direct Function Call Mapping ---
# Maps an endpoint path to the actual Python function that handles it.
# This avoids making an HTTP request to ourselves (which causes a deadlock).
DIRECT_CALL_MAP = {
    # 💰 Financial Analytics (NEW!)
    "/admin/financial/company-summary/today": get_company_financial_summary_today,
    "/admin/financial/revenue-only/company-total/today": get_company_revenue_total_today,
    "/admin/financial/profit-only/company-total/today": get_company_profit_total_today,
    "/admin/financial/dealership/{dealership_id}/summary": get_dealership_financial_summary,
    "/admin/financial/dealership/{dealership_id}/detailed-breakdown": get_dealership_detailed_breakdown,
    "/admin/financial/all-dealerships/summary": get_all_dealerships_financial_summary,
    "/admin/financial/date-range/summary": get_date_range_financial_summary,
    "/admin/financial/top-performers/today": get_top_performers_today,
    
    # 🏢 Labor Analytics
    "/admin/analytics/all-dealerships/labor-costs-today": get_all_dealerships_labor_costs_today,
    "/admin/analytics/labor/daily/enhanced": get_enhanced_daily_labor_spend,
    "/admin/analytics/labor/weekly": get_weekly_labor_spend,
    "/admin/analytics/dealership/{dealership_id}/comprehensive-labor-spend": get_comprehensive_labor_spend,
    "/admin/analytics/dealership/{dealership_id}/labor-preview": get_labor_preview,
    "/admin/analytics/active/dealership/{dealership_id}": get_active_employees_by_dealership,
    "/admin/analytics/dealership/{dealership_id}/employee-hours": get_dealership_employee_hours_breakdown,
    "/admin/analytics/active/all": get_all_active_employees,
    "/admin/analytics/employee/{employee_id}/details": get_employee_details,
    "/admin/analytics/employees/details": get_all_employees_details,
    
    # 👥 Employee Management
    "/admin/user-requests/users": list_all_users_for_admin,
    "/admin/user-requests/users/wages": list_all_user_wages_for_admin,
    "/admin/user-requests/users/{user_id}/wage": get_user_wage,  # GET version
    
    # ⏰ Time Management
    "/admin/time/employee/{employee_id}/recent-punches": get_employee_recent_punches,
    "/admin/time/recent-entries": get_recent_global_entries,
    "/admin/time/employee/{employee_id}/changes": get_employee_admin_changes,
    
    # 🏖️ Vacation Management
    "/admin/vacation/vacation-entries": get_vacation_entries,
    "/admin/vacation/employee/{employee_id}/vacation": get_employee_vacation_entries,
    "/admin/vacation/recent-activity": get_recent_combined_activity,
    "/admin/vacation/types": get_vacation_types,
    
    # 📋 Clock Request Management
    "/admin/clock-requests/all": get_all_clock_requests,
    
    # Add other fast endpoints here in the future
}

@router.post("/vapi-webhook")
async def handle_vapi_webhook(
    message: VapiWebhook,
    x_vapi_secret: Optional[str] = Header(None, alias="x-vapi-secret")
):
    """
    Securely handles function calls from the Vapi voice agent by calling
    internal application functions directly, avoiding network deadlocks.
    
    🚀 EXECUTIVE ENDPOINT MAPPINGS (39+ Fast Direct Calls):
    
    💰 Financial Analytics (8 endpoints):
    - Company financial summary, revenue, profit
    - Individual dealership breakdowns  
    - All dealerships comparison
    - Date range analysis & top performers
    
    🏢 Labor Analytics (10 endpoints):
    - Real-time labor costs across all dealerships
    - Daily/weekly labor spend analysis
    - Employee productivity & hours breakdown
    - Active employee monitoring by location
    
    👥 Employee Management (3 endpoints):
    - User directory & wage management
    - Individual employee wage lookup
    
    ⏰ Time Management (3 endpoints):
    - Employee punch history & admin changes
    - Recent time entries across system
    
    🏖️ Vacation Management (4 endpoints):
    - Vacation entries & employee history
    - Recent activity & vacation types
    
    📋 Clock Request Management (1 endpoint):
    - All clock change requests
    
    All endpoints bypass HTTP self-calls for maximum performance! 🔥
    """
    # 1. Authenticate the webhook request from Vapi
    if not x_vapi_secret or x_vapi_secret != VAPI_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing x-vapi-secret header")

    # 2. Process only "function-call" messages
    if message.type != "function-call" or not message.functionCall:
        return {"message": "Request processed. No action taken."}

    # 3. Ensure it's for our 'getCompanyData' tool
    if message.functionCall.name != "getCompanyData":
        raise HTTPException(status_code=400, detail=f"Unsupported function: {message.functionCall.name}")

    params = message.functionCall.parameters
    endpoint_path = params.endpoint_path
    
    logger.info(f"Vapi webhook processing request for endpoint: {endpoint_path}")

    # 4. Fetch the admin auth token
    try:
        token_response = requests.post(VAPI_TOKEN_URL, timeout=10)
        token_response.raise_for_status()
        auth_token = token_response.json().get("authToken")
        if not auth_token:
            raise HTTPException(status_code=500, detail="Failed to retrieve authentication token")
    except requests.RequestException as e:
        logger.error(f"Failed to fetch Vapi auth token: {e}")
        raise HTTPException(status_code=502, detail=f"Error fetching auth token: {e}")

    # 5. Route to the appropriate function (direct call or HTTP fallback)
    if endpoint_path in DIRECT_CALL_MAP:
        # Use the efficient direct function call
        api_data = await _execute_direct_call(endpoint_path, params, auth_token)
    else:
        # Fallback to HTTP for non-mapped or slow endpoints
        # Note: This may still cause timeouts for slow endpoints.
        api_data = await _execute_http_call(endpoint_path, params, auth_token)

    # 6. Return the result to Vapi
    return VapiResponse(
        tool_results=[
            ToolResult(
                tool_call_id=message.functionCall.tool_call_id,
                result=api_data
            )
        ]
    )

async def _execute_direct_call(endpoint_path: str, params: FunctionParameters, token: str):
    """
    Executes a Python function directly based on the endpoint path.
    This is the preferred method as it's fast and avoids network deadlocks.
    """
    logger.info(f"Executing direct call for: {endpoint_path}")
    target_function = DIRECT_CALL_MAP[endpoint_path]
    
    # Manually resolve dependencies for the target function
    try:
        session: Session = next(get_session())
        admin_user: dict = require_admin_role_from_token(token)
        
        # Prepare arguments from path and query parameters
        kwargs = {**(params.path_params or {}), **(params.query_params or {})}
        
        # Call the target function with resolved dependencies and arguments
        result = await target_function(session=session, admin_user=admin_user, **kwargs)
        return result
        
    except Exception as e:
        logger.error(f"Error during direct function call for {endpoint_path}: {e}")
        raise HTTPException(status_code=500, detail=f"Internal error processing direct call: {str(e)}")
    finally:
        # Ensure the session is closed
        if 'session' in locals() and session:
            session.close()

async def _execute_http_call(endpoint_path: str, params: FunctionParameters, token: str):
    """
    Fallback method to make an HTTP request.
    Used for endpoints not yet mapped for direct calls.
    """
    logger.warning(f"Executing HTTP fallback for: {endpoint_path}")
    
    # Construct the full internal URL
    # INTERNAL_API_BASE_URL is now correctly set in the deployment script
    base_url = os.getenv("INTERNAL_API_BASE_URL", "http://127.0.0.1:8000")
    api_url = f"{base_url}{endpoint_path}"

    if params.path_params:
        api_url = api_url.format(**params.path_params)

    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(api_url, headers=headers, params=params.query_params, timeout=120)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logger.error(f"HTTP fallback call for {endpoint_path} failed: {e}")
        raise HTTPException(status_code=502, detail=f"HTTP call failed: {str(e)}") 