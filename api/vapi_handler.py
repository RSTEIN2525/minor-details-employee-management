import os
import logging
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel
import json
from sqlmodel import Session

# Import the functions we want to call directly
from api.admin_analytics_routes import (
    get_employee_details,
    get_active_employees_by_dealership,
    get_dealership_employee_hours_breakdown,
    get_comprehensive_labor_spend,
    get_labor_preview,
    get_all_active_employees,
    get_all_employees_details,
    get_enhanced_daily_labor_spend,
    get_weekly_labor_spend,
    get_all_dealerships_labor_costs_today,
    get_dealership_labor_spend
)

from api.admin_financial_routes import (
    get_dealership_financial_summary,
    get_company_financial_summary_today,
    get_all_dealerships_financial_summary,
    get_company_revenue_total_today,
    get_company_profit_total_today,
    get_dealership_detailed_breakdown,
    get_date_range_financial_summary,
    get_top_performers_today
)

from api.admin_user_routes import (
    list_all_users_for_admin,
    list_all_user_wages_for_admin,
    set_or_update_user_wage,
    get_user_wage
)

from api.admin_time_routes import (
    get_employee_recent_punches,
    get_recent_global_entries,
    get_employee_admin_changes,
    admin_direct_single_clock_creation,
    admin_direct_single_clock_edit,
    admin_direct_single_clock_delete,
    admin_direct_change_punch_dealership
)

from api.admin_vacation_routes import (
    grant_vacation_time,
    get_vacation_entries,
    get_employee_vacation_entries,
    get_recent_combined_activity,
    get_vacation_types
)

from api.admin_clock_request_routes import (
    get_all_clock_requests,
    approve_clock_request,
    deny_clock_request
)

from api.admin_device_routes import (
    list_pending_device_requests,
    approve_device_request,
    list_approved_device_requests,
    get_user_approved_devices
)

from api.admin_shop_routes import (
    list_all_shops,
    create_shop,
    update_shop
)

from api.admin_injury_routes import (
    get_injury_reports,
    get_employee_injury_reports,
    get_dealership_injury_summary
)

from api.admin_dealership_routes import (
    list_all_dealerships
)

from core.deps import get_session, require_admin_role_from_token
from core.firebase import db as firestore_db

# Configure logging
logger = logging.getLogger(__name__)

router = APIRouter()

# Environment variables
VAPI_SECRET_TOKEN = os.getenv("VAPI_SECRET_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize OpenAI client
try:
    import openai
    openai.api_key = OPENAI_API_KEY
    OPENAI_AVAILABLE = True
except ImportError:
    logger.warning("OpenAI package not available. Smart matching will be disabled.")
    OPENAI_AVAILABLE = False
    openai = None

# Pydantic models for request validation
class WorkflowParameters(BaseModel):
    action: str  # e.g., "get_employee_details", "get_dealership_status"
    user_input: str  # The spoken text from user
    token: str  # Auth token passed from VAPI

class VapiWorkflow(BaseModel):
    type: str
    workflow: Optional[WorkflowParameters] = None

# Response model for workflow results
class WorkflowResult(BaseModel):
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None
    endpoint_called: Optional[str] = None  # Track what function/endpoint was executed
    action_detected: Optional[str] = None  # Track what AI action was detected

class VapiResponse(BaseModel):
    success: bool
    data: Optional[Any] = None
    message: Optional[str] = None
    action_detected: Optional[str] = None  # Track what AI action was detected
    endpoint_called: Optional[str] = None  # Track what function/endpoint was executed

# Cache for employees and dealerships (refresh every hour)
_employee_cache = {"data": None, "timestamp": 0}
_dealership_cache = {"data": None, "timestamp": 0}
CACHE_TTL = 3600  # 1 hour

def fallback_action_detection(user_input: str) -> Optional[str]:
    """Simple keyword-based action detection when OpenAI isn't available"""
    user_lower = user_input.lower()
    
    # Financial keywords
    if any(word in user_lower for word in ["financial", "revenue", "profit", "money", "cost"]):
        if any(word in user_lower for word in ["company", "total", "all"]):
            return "get_company_financial_summary"
        else:
            return "get_dealership_financial"
    
    # Labor keywords
    if any(word in user_lower for word in ["labor", "working", "active", "employees"]):
        if any(word in user_lower for word in ["all", "everyone", "company"]):
            return "get_all_active_employees"
        else:
            return "get_dealership_employees"
    
    # Employee keywords
    if any(word in user_lower for word in ["employee", "worker", "details", "performance"]):
        return "get_employee_details"
    
    # Default to company overview
    return "get_company_financial_summary"

def fallback_entity_matching(user_input: str, candidates: List[Dict], match_type: str) -> Optional[Dict]:
    """Simple name matching when OpenAI isn't available"""
    user_lower = user_input.lower()
    
    # Try exact name match first
    for candidate in candidates:
        name = candidate["name"].lower()
        if name in user_lower or any(part in user_lower for part in name.split()):
            return candidate
    
    # If no match, return first candidate as fallback
    return candidates[0] if candidates else None

async def get_all_employees_cached():
    """Get all employees with caching"""
    import time
    current_time = time.time()
    
    if (_employee_cache["data"] is None or 
        current_time - _employee_cache["timestamp"] > CACHE_TTL):
        
        logger.info("Refreshing employee cache...")
        try:
            # Get all employees from Firestore
            users_ref = firestore_db.collection("users").where(
                "role", "in", ["employee", "clockOnlyEmployee", "minorDetailsManager", "minorDetailsSupervisor"]
            ).stream()
            
            employees = []
            for doc in users_ref:
                user_data = doc.to_dict()
                employees.append({
                    "id": doc.id,
                    "name": user_data.get("displayName", "Unknown"),
                    "role": user_data.get("role", "employee")
                })
            
            _employee_cache["data"] = employees
            _employee_cache["timestamp"] = current_time
            logger.info(f"Cached {len(employees)} employees")
            
        except Exception as e:
            logger.error(f"Error fetching employees: {str(e)}")
            return []
    
    return _employee_cache["data"]

async def get_all_dealerships_cached():
    """Get all dealerships with caching"""
    import time
    current_time = time.time()
    
    if (_dealership_cache["data"] is None or 
        current_time - _dealership_cache["timestamp"] > CACHE_TTL):
        
        logger.info("Refreshing dealership cache...")
        try:
            admin_user = {"role": "admin"}
            dealerships = await list_all_dealerships(admin_user=admin_user)
            
            _dealership_cache["data"] = dealerships
            _dealership_cache["timestamp"] = current_time
            logger.info(f"Cached {len(dealerships)} dealerships")
            
        except Exception as e:
            logger.error(f"Error fetching dealerships: {str(e)}")
            return []
    
    return _dealership_cache["data"]

async def determine_action_with_llm(user_input: str) -> Optional[str]:
    """Use OpenAI to determine what action the user wants to perform"""
    if not OPENAI_AVAILABLE:
        return fallback_action_detection(user_input)
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4.1",
            messages=[
                {
                    "role": "system",
                    "content": """You are an AI that determines what action a user wants to perform based on their natural language input.

AVAILABLE ACTIONS:

COMPANY-WIDE ACTIONS:
- get_company_financial_summary: Company revenue, profit, financial overview
- get_company_revenue: Total company revenue
- get_company_profit: Company profit/loss
- get_all_dealerships_financial: Financial summary for all dealerships
- get_top_financial_performers: Top performing dealerships
- get_all_dealerships_labor_costs: Labor costs across all dealerships
- get_enhanced_daily_labor: Enhanced daily labor analysis
- get_weekly_labor: Weekly labor trends
- get_all_active_employees: All currently active employees
- get_all_employees_details: Details for all employees
- get_all_users: List of all users
- get_all_user_wages: Wage information for all employees
- get_recent_global_entries: Recent time entries company-wide
- get_all_vacation_entries: All vacation entries
- get_recent_activity: Recent admin activity
- get_vacation_types: Available vacation types
- get_clock_requests: All clock change requests
- get_pending_devices: Pending device approvals
- get_approved_devices: Recently approved devices
- get_all_shops: All business locations
- get_all_dealerships: All dealerships
- get_injury_reports: Workplace injury reports

EMPLOYEE-SPECIFIC ACTIONS:
- get_employee_details: Individual employee information
- get_employee_wage: Employee wage information
- get_employee_recent_punches: Recent punch history
- get_employee_admin_changes: Admin changes to employee
- get_employee_vacation: Employee vacation history
- get_employee_devices: Employee's approved devices
- get_employee_injuries: Employee injury history

DEALERSHIP-SPECIFIC ACTIONS:
- get_dealership_financial: Dealership financial summary
- get_dealership_detailed_breakdown: Detailed financial breakdown for dealership
- get_dealership_labor: Dealership labor costs
- get_dealership_comprehensive_labor: Comprehensive labor analysis for dealership
- get_dealership_labor_preview: Labor cost preview for dealership
- get_dealership_active_employees: Active employees at specific dealership
- get_dealership_employee_hours: Employee hours breakdown for dealership
- get_dealership_injury_stats: Dealership injury statistics

Respond with ONLY the action name, nothing else."""
                },
                {
                    "role": "user",
                    "content": f"What action does this request require: '{user_input}'"
                }
            ],
            max_tokens=50,
            temperature=0.1
        )
        
        action = response.choices[0].message.content.strip()
        logger.info(f"LLM determined action: {action}")
        return action
        
    except Exception as e:
        logger.error(f"Error using OpenAI for action detection: {str(e)}")
        return fallback_action_detection(user_input)

async def find_best_match_with_llm(user_input: str, candidates: List[Dict], match_type: str) -> Optional[Dict]:
    """Use OpenAI to find the best matching employee or dealership"""
    if not OPENAI_AVAILABLE or not candidates:
        return fallback_entity_matching(user_input, candidates, match_type)
    
    try:
        candidates_text = "\n".join([f"ID: {c['id']}, Name: {c['name']}" for c in candidates])
        
        response = openai.ChatCompletion.create(
            model="gpt-4.1",
            messages=[
                {
                    "role": "system",
                    "content": f"""You are an AI that matches user input to the best {match_type} from a list.
Consider:
- Exact name matches
- Partial name matches
- Common abbreviations
- Phonetic similarities
- Nicknames or shortened versions

Respond with ONLY the ID of the best match, nothing else. If no good match, respond with "NONE"."""
                },
                {
                    "role": "user",
                    "content": f"Find the best {match_type} match for: '{user_input}'\n\nCandidates:\n{candidates_text}"
                }
            ],
            max_tokens=50,
            temperature=0.1
        )
        
        match_id = response.choices[0].message.content.strip()
        
        if match_id == "NONE":
            return None
            
        # Find the candidate with matching ID
        for candidate in candidates:
            if candidate["id"] == match_id:
                logger.info(f"LLM matched '{user_input}' to {match_type}: {candidate['name']}")
                return candidate
        
        # Fallback to simple matching if LLM returned invalid ID
        return fallback_entity_matching(user_input, candidates, match_type)
        
    except Exception as e:
        logger.error(f"Error using OpenAI for entity matching: {str(e)}")
        return fallback_entity_matching(user_input, candidates, match_type)

async def handle_company_wide_workflow(action: str, user_input: str, token: str) -> WorkflowResult:
    """Handle company-wide workflows"""
    try:
        admin_user = require_admin_role_from_token(token)
        session = next(get_session())
        
        try:
            # Financial Analytics
            if action == "get_company_financial_summary":
                result = await get_company_financial_summary_today(session=session, admin=admin_user)
                message = "Retrieved company financial summary for today"
                endpoint = "get_company_financial_summary_today"
            elif action == "get_company_revenue":
                result = await get_company_revenue_total_today(session=session, admin=admin_user)
                message = "Retrieved total company revenue for today"
                endpoint = "get_company_revenue_total_today"
            elif action == "get_company_profit":
                result = await get_company_profit_total_today(session=session, admin=admin_user)
                message = "Retrieved company profit/loss for today"
                endpoint = "get_company_profit_total_today"
            elif action == "get_all_dealerships_financial":
                result = await get_all_dealerships_financial_summary(session=session, admin=admin_user)
                message = "Retrieved financial summary for all dealerships"
                endpoint = "get_all_dealerships_financial_summary"
            elif action == "get_top_financial_performers":
                result = await get_top_performers_today(session=session, admin=admin_user)
                message = "Retrieved top performing dealerships"
                endpoint = "get_top_performers_today"
            
            # Labor Analytics
            elif action == "get_all_dealerships_labor_costs":
                result = await get_all_dealerships_labor_costs_today(session=session, admin_user=admin_user)
                message = "Retrieved labor costs for all dealerships"
                endpoint = "get_all_dealerships_labor_costs_today"
            elif action == "get_enhanced_daily_labor":
                result = await get_enhanced_daily_labor_spend(session=session, admin_user=admin_user)
                message = "Retrieved enhanced daily labor analysis"
                endpoint = "get_enhanced_daily_labor_spend"
            elif action == "get_weekly_labor":
                result = await get_weekly_labor_spend(session=session, admin_user=admin_user)
                message = "Retrieved weekly labor trends"
                endpoint = "get_weekly_labor_spend"
            elif action == "get_all_active_employees":
                result = await get_all_active_employees(session=session, admin_user=admin_user)
                message = "Retrieved all active employees"
                endpoint = "get_all_active_employees"
            
            # Employee Management
            elif action == "get_all_employees_details":
                result = await get_all_employees_details(session=session, admin_user=admin_user)
                message = "Retrieved details for all employees"
                endpoint = "get_all_employees_details"
            elif action == "get_all_users":
                result = await list_all_users_for_admin(admin_user=admin_user)
                message = "Retrieved list of all users"
                endpoint = "list_all_users_for_admin"
            elif action == "get_all_user_wages":
                result = await list_all_user_wages_for_admin(admin_user=admin_user)
                message = "Retrieved wage information for all employees"
                endpoint = "list_all_user_wages_for_admin"
            
            # Time Management
            elif action == "get_recent_global_entries":
                result = await get_recent_global_entries(session=session, admin_user=admin_user)
                message = "Retrieved recent time entries across all employees"
                endpoint = "get_recent_global_entries"
            
            # Vacation Management
            elif action == "get_all_vacation_entries":
                result = await get_vacation_entries(session=session, admin_user=admin_user)
                message = "Retrieved all vacation entries"
                endpoint = "get_vacation_entries"
            elif action == "get_recent_activity":
                result = await get_recent_combined_activity(session=session, admin_user=admin_user)
                message = "Retrieved recent admin activity"
                endpoint = "get_recent_combined_activity"
            elif action == "get_vacation_types":
                result = await get_vacation_types(session=session, admin_user=admin_user)
                message = "Retrieved available vacation types"
                endpoint = "get_vacation_types"
            
            # Clock Requests
            elif action == "get_clock_requests":
                result = await get_all_clock_requests(session=session, admin_user=admin_user)
                message = "Retrieved all clock change requests"
                endpoint = "get_all_clock_requests"
            
            # Device Management
            elif action == "get_pending_devices":
                result = await list_pending_device_requests(admin_user=admin_user)
                message = "Retrieved pending device approval requests"
                endpoint = "list_pending_device_requests"
            elif action == "get_approved_devices":
                result = await list_approved_device_requests(admin_user=admin_user)
                message = "Retrieved recently approved devices"
                endpoint = "list_approved_device_requests"
            
            # Shop/Location Management
            elif action == "get_all_shops":
                result = await list_all_shops(admin_user=admin_user)
                message = "Retrieved all business locations"
                endpoint = "list_all_shops"
            elif action == "get_all_dealerships":
                result = await list_all_dealerships(admin_user=admin_user)
                message = "Retrieved all dealerships"
                endpoint = "list_all_dealerships"
            
            # Safety & Injury Reporting
            elif action == "get_injury_reports":
                result = await get_injury_reports(session=session, admin_user=admin_user)
                message = "Retrieved workplace injury reports"
                endpoint = "get_injury_reports"
            
            else:
                return WorkflowResult(
                    success=False, 
                    message=f"Unknown company-wide action: {action}",
                    action_detected=action,
                    endpoint_called="none"
                )
            
            return WorkflowResult(
                success=True, 
                data=result, 
                message=message,
                endpoint_called=endpoint,
                action_detected=action
            )
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error in company-wide workflow: {str(e)}")
        return WorkflowResult(
            success=False, 
            message=f"Error retrieving company data: {str(e)}",
            action_detected=action,
            endpoint_called="error"
        )

async def handle_employee_specific_workflow(action: str, employee: Dict, user_input: str, token: str) -> WorkflowResult:
    """Handle employee-specific workflows"""
    employee_id = employee["id"]
    employee_name = employee["name"]
    
    try:
        admin_user = require_admin_role_from_token(token)
        session = next(get_session())
        
        try:
            if action == "get_employee_details":
                result = await get_employee_details(employee_id=employee_id, session=session, admin_user=admin_user)
                message = f"Retrieved details for {employee_name}"
                endpoint = "get_employee_details"
            elif action == "get_employee_wage":
                result = await get_user_wage(user_id=employee_id, admin_user=admin_user)
                message = f"Retrieved wage for {employee_name}"
                endpoint = "get_user_wage"
            elif action == "get_employee_recent_punches":
                result = await get_employee_recent_punches(employee_id=employee_id, session=session, admin_user=admin_user)
                message = f"Retrieved recent punches for {employee_name}"
                endpoint = "get_employee_recent_punches"
            elif action == "get_employee_admin_changes":
                result = await get_employee_admin_changes(employee_id=employee_id, session=session, admin_user=admin_user)
                message = f"Retrieved admin changes for {employee_name}"
                endpoint = "get_employee_admin_changes"
            elif action == "get_employee_vacation":
                result = await get_employee_vacation_entries(employee_id=employee_id, session=session, admin_user=admin_user)
                message = f"Retrieved vacation history for {employee_name}"
                endpoint = "get_employee_vacation_entries"
            elif action == "get_employee_devices":
                result = await get_user_approved_devices(user_id=employee_id, admin_user=admin_user)
                message = f"Retrieved devices for {employee_name}"
                endpoint = "get_user_approved_devices"
            elif action == "get_employee_injuries":
                result = await get_employee_injury_reports(employee_id=employee_id, session=session, admin_user=admin_user)
                message = f"Retrieved injury history for {employee_name}"
                endpoint = "get_employee_injury_reports"
            elif action == "update_employee_wage":
                return WorkflowResult(
                    success=False, 
                    message="Wage updates require wage amount parameter. Use the direct API endpoint.",
                    action_detected=action,
                    endpoint_called="none"
                )
            else:
                return WorkflowResult(
                    success=False, 
                    message=f"Unknown employee action: {action}",
                    action_detected=action,
                    endpoint_called="none"
                )
            
            return WorkflowResult(
                success=True, 
                data=result, 
                message=message,
                endpoint_called=endpoint,
                action_detected=action
            )
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error in employee workflow: {str(e)}")
        return WorkflowResult(
            success=False, 
            message=f"Error retrieving employee data: {str(e)}",
            action_detected=action,
            endpoint_called="error"
        )

async def handle_dealership_specific_workflow(action: str, dealership: Dict, user_input: str, token: str) -> WorkflowResult:
    """Handle dealership-specific workflows"""
    dealership_id = dealership["id"]
    dealership_name = dealership["name"]
    
    try:
        admin_user = require_admin_role_from_token(token)
        session = next(get_session())
        
        try:
            if action == "get_dealership_financial":
                result = await get_dealership_financial_summary(dealership_id=dealership_id, session=session, admin=admin_user)
                message = f"Retrieved financial summary for {dealership_name}"
                endpoint = "get_dealership_financial_summary"
            elif action == "get_dealership_detailed_breakdown":
                result = await get_dealership_detailed_breakdown(dealership_id=dealership_id, session=session, admin=admin_user)
                message = f"Retrieved detailed financial breakdown for {dealership_name}"
                endpoint = "get_dealership_detailed_breakdown"
            elif action == "get_dealership_labor":
                result = await get_dealership_labor_spend(dealership_id=dealership_id, session=session, admin_user=admin_user)
                message = f"Retrieved labor costs for {dealership_name}"
                endpoint = "get_dealership_labor_spend"
            elif action == "get_dealership_comprehensive_labor":
                result = await get_comprehensive_labor_spend(dealership_id=dealership_id, session=session, admin_user=admin_user)
                message = f"Retrieved comprehensive labor analysis for {dealership_name}"
                endpoint = "get_comprehensive_labor_spend"
            elif action == "get_dealership_labor_preview":
                result = await get_labor_preview(dealership_id=dealership_id, session=session, admin_user=admin_user)
                message = f"Retrieved labor cost preview for {dealership_name}"
                endpoint = "get_labor_preview"
            elif action == "get_dealership_active_employees":
                result = await get_active_employees_by_dealership(dealership_id=dealership_id, session=session, admin_user=admin_user)
                message = f"Retrieved active employees at {dealership_name}"
                endpoint = "get_active_employees_by_dealership"
            elif action == "get_dealership_employee_hours":
                result = await get_dealership_employee_hours_breakdown(dealership_id=dealership_id, session=session, admin_user=admin_user)
                message = f"Retrieved employee hours breakdown for {dealership_name}"
                endpoint = "get_dealership_employee_hours_breakdown"
            elif action == "get_dealership_injury_stats":
                result = await get_dealership_injury_summary(dealership_id=dealership_id, session=session, admin_user=admin_user)
                message = f"Retrieved injury statistics for {dealership_name}"
                endpoint = "get_dealership_injury_summary"
            else:
                return WorkflowResult(
                    success=False, 
                    message=f"Unknown dealership action: {action}",
                    action_detected=action,
                    endpoint_called="none"
                )
            
            return WorkflowResult(
                success=True, 
                data=result, 
                message=message,
                endpoint_called=endpoint,
                action_detected=action
            )
            
        finally:
            session.close()
            
    except Exception as e:
        logger.error(f"Error in dealership workflow: {str(e)}")
        return WorkflowResult(
            success=False, 
            message=f"Error retrieving dealership data: {str(e)}",
            action_detected=action,
            endpoint_called="error"
        )

@router.post("/vapi-webhook")
async def handle_vapi_webhook(
    message: VapiWorkflow,
    x_vapi_secret: Optional[str] = Header(None, alias="x-vapi-secret")
):
    """
    🚀 COMPREHENSIVE EXECUTIVE WORKFLOW HANDLER with Endpoint Tracking
    
    NOW INCLUDES endpoint_called and action_detected in all responses!
    
    Examples of response format:
    {
        "success": true,
        "data": {...},
        "message": "Retrieved financial summary for Toyota",
        "action_detected": "get_dealership_financial",
        "endpoint_called": "get_dealership_financial_summary"
    }
    """
    
    # 1. Authenticate the webhook request from Vapi
    if not x_vapi_secret or x_vapi_secret != VAPI_SECRET_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing x-vapi-secret header")

    # 2. Process only "workflow" messages
    if message.type != "workflow" or not message.workflow:
        return VapiResponse(
            success=False, 
            message="Request processed. No workflow action taken.",
            action_detected="none",
            endpoint_called="none"
        )

    workflow = message.workflow
    action = workflow.action
    user_input = workflow.user_input
    token = workflow.token
    
    logger.info(f"Processing workflow: {action} with input: '{user_input}'")

    # 3. Route to smart workflow handler
    try:
        # Always use smart auto-detection workflow for best results
        determined_action = await determine_action_with_llm(user_input)
        
        if not determined_action:
            return VapiResponse(
                success=False,
                data=None,
                message="I couldn't understand your request. Please try being more specific.",
                action_detected="unknown",
                endpoint_called="none"
            )
        
        # === COMPANY-WIDE ACTIONS ===
        if determined_action in [
            "get_company_financial_summary", "get_company_revenue", "get_company_profit",
            "get_all_dealerships_financial", "get_top_financial_performers",
            "get_all_dealerships_labor_costs", "get_enhanced_daily_labor", "get_weekly_labor",
            "get_all_active_employees", "get_all_employees_details", "get_all_users", "get_all_user_wages",
            "get_recent_global_entries", "get_all_vacation_entries", "get_recent_activity", "get_vacation_types",
            "get_clock_requests", "get_pending_devices", "get_approved_devices",
            "get_all_shops", "get_all_dealerships", "get_injury_reports"
        ]:
            workflow_result = await handle_company_wide_workflow(determined_action, user_input, token)
        
        # === EMPLOYEE-SPECIFIC ACTIONS ===
        elif determined_action in [
            "get_employee_details", "get_employee_wage", "get_employee_recent_punches",
            "get_employee_admin_changes", "get_employee_vacation", "get_employee_devices",
            "get_employee_injuries", "update_employee_wage"
        ]:
            employees = await get_all_employees_cached()
            if not employees:
                return VapiResponse(
                    success=False,
                    data=None,
                    message="No employees found in the system.",
                    action_detected=determined_action,
                    endpoint_called="none"
                )
            
            employee = await find_best_match_with_llm(user_input, employees, "employee")
            if not employee:
                return VapiResponse(
                    success=False,
                    data=None,
                    message="Could not identify which employee you're referring to. Please be more specific.",
                    action_detected=determined_action,
                    endpoint_called="none"
                )
            
            workflow_result = await handle_employee_specific_workflow(determined_action, employee, user_input, token)
        
        # === DEALERSHIP-SPECIFIC ACTIONS ===
        elif determined_action in [
            "get_dealership_financial", "get_dealership_detailed_breakdown", "get_dealership_labor",
            "get_dealership_comprehensive_labor", "get_dealership_labor_preview", "get_dealership_active_employees",
            "get_dealership_employee_hours", "get_dealership_injury_stats"
        ]:
            dealerships = await get_all_dealerships_cached()
            if not dealerships:
                return VapiResponse(
                    success=False,
                    data=None,
                    message="No dealerships found in the system.",
                    action_detected=determined_action,
                    endpoint_called="none"
                )
            
            dealership = await find_best_match_with_llm(user_input, dealerships, "dealership")
            if not dealership:
                return VapiResponse(
                    success=False,
                    data=None,
                    message="Could not identify which dealership you're referring to. Please be more specific.",
                    action_detected=determined_action,
                    endpoint_called="none"
                )
            
            workflow_result = await handle_dealership_specific_workflow(determined_action, dealership, user_input, token)
        
        else:
            logger.warning(f"Could not classify action. Raw input: {user_input}")
            return VapiResponse(
                success=False,
                data=None,
                message="I couldn't understand your request. Please try being more specific.",
                action_detected="unknown",
                endpoint_called="none"
            )
        
        # Return the workflow result with endpoint information
        return VapiResponse(
            success=workflow_result.success,
            data=workflow_result.data,
            message=workflow_result.message,
            action_detected=workflow_result.action_detected,
            endpoint_called=workflow_result.endpoint_called
        )
        
    except Exception as e:
        logger.error(f"Error processing workflow: {str(e)}")
        return VapiResponse(
            success=False,
            data=None,
            message=f"Error processing request: {str(e)}",
            action_detected=determined_action or "unknown",
            endpoint_called="error"
        ) 