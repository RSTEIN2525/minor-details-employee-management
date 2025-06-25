from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, date, timedelta
from db.session import get_session
from core.deps import require_admin_role
from core.firebase import db as firestore_db
from pydantic import BaseModel, field_serializer
from utils.datetime_helpers import format_utc_datetime
from collections import defaultdict
import asyncio

router = APIRouter()

# --- Response Models ---

class DealershipFinancialSummary(BaseModel):
    dealership_id: str
    dealership_name: Optional[str] = None
    
    # Revenue Breakdown
    ticket_revenue: float = 0.0
    wash_revenue: float = 0.0
    photo_revenue: float = 0.0
    lot_prep_revenue: float = 0.0
    total_revenue: float = 0.0
    
    # Counts
    ticket_count: int = 0
    wash_count: int = 0
    photo_count: int = 0
    lot_prep_count: int = 0
    
    # Profit Analysis (requires labor data)
    labor_cost: float = 0.0
    profit_loss: float = 0.0
    labor_percentage: float = 0.0

class ServiceBreakdown(BaseModel):
    service_type: str
    count: int
    revenue: float

class DealershipDetailedBreakdown(BaseModel):
    dealership_id: str
    dealership_name: Optional[str] = None
    
    # Service breakdowns
    ticket_services: List[ServiceBreakdown] = []
    wash_breakdown: ServiceBreakdown
    photo_breakdown: ServiceBreakdown
    lot_prep_breakdown: ServiceBreakdown
    
    # Totals
    total_revenue: float = 0.0
    total_count: int = 0
    labor_cost: float = 0.0
    profit_loss: float = 0.0

class CompanyWideSummary(BaseModel):
    analysis_date: str
    analysis_timestamp: datetime
    
    # Company Totals
    total_revenue: float = 0.0
    total_labor_cost: float = 0.0
    total_profit_loss: float = 0.0
    
    # Revenue Breakdown
    total_ticket_revenue: float = 0.0
    total_wash_revenue: float = 0.0
    total_photo_revenue: float = 0.0
    total_lot_prep_revenue: float = 0.0
    
    # Counts
    total_tickets: int = 0
    total_washes: int = 0
    total_photos: int = 0
    total_lot_preps: int = 0
    
    # Dealership Data
    dealership_count: int = 0
    profitable_dealerships: int = 0
    
    @field_serializer('analysis_timestamp')
    def serialize_timestamp(self, dt: datetime) -> str:
        return format_utc_datetime(dt)

class DateRangeFinancialSummary(BaseModel):
    start_date: str
    end_date: str
    date_range_days: int
    
    # Totals for the range
    total_revenue: float = 0.0
    total_labor_cost: float = 0.0
    total_profit_loss: float = 0.0
    
    # Daily averages
    avg_daily_revenue: float = 0.0
    avg_daily_labor_cost: float = 0.0
    avg_daily_profit: float = 0.0
    
    # Breakdown by dealership
    dealership_summaries: List[DealershipFinancialSummary] = []

class TopPerformersResponse(BaseModel):
    analysis_date: str
    
    # Top by revenue
    top_revenue_dealerships: List[DealershipFinancialSummary] = []
    
    # Top by profit
    top_profit_dealerships: List[DealershipFinancialSummary] = []
    
    # Top by volume
    top_volume_dealerships: List[DealershipFinancialSummary] = []

# --- Helper Functions ---

async def get_dealership_name(dealership_id: str) -> str:
    """Get dealership display name from Firestore"""
    try:
        doc_ref = firestore_db.collection("dealerships").document(dealership_id)
        doc = doc_ref.get()
        if doc.exists:
            data = doc.to_dict()
            return data.get("name", dealership_id)
    except Exception as e:
        print(f"Error fetching dealership name for {dealership_id}: {e}")
    return dealership_id

async def get_all_dealership_names() -> Dict[str, str]:
    """Get all dealership names as a lookup map"""
    try:
        dealerships_ref = firestore_db.collection("dealerships").stream()
        name_map = {}
        for doc in dealerships_ref:
            data = doc.to_dict()
            name_map[doc.id] = data.get("name", doc.id)
        return name_map
    except Exception as e:
        print(f"Error fetching dealership names: {e}")
        return {}

async def get_firestore_financial_data(dealership_ids: List[str], target_date: date) -> Dict[str, Dict[str, Any]]:
    """Fetch tickets, washes, photos, and lot prep data from Firestore for given dealerships and date"""
    
    date_folder = target_date.strftime("%Y-%m-%d")
    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    
    dealership_data = {}
    
    # Initialize data structure for each dealership
    for dealership_id in dealership_ids:
        dealership_data[dealership_id] = {
            "tickets": [],
            "washes": [],
            "photos": [],
            "lot_prep": [],
            "ticket_revenue": 0.0,
            "wash_revenue": 0.0,
            "photo_revenue": 0.0,
            "lot_prep_revenue": 0.0,
            "ticket_count": 0,
            "wash_count": 0,
            "photo_count": 0,
            "lot_prep_count": 0
        }
    
    # Fetch tickets from Firestore
    try:
        tickets_ref = firestore_db.collection("tickets")
        tickets_query = tickets_ref.where("dealership", "in", dealership_ids).where("ticketState", "in", ["pending", "closed"])
        tickets = tickets_query.stream()
        
        for ticket_doc in tickets:
            ticket_data = ticket_doc.to_dict()
            if ticket_data.get("completionDetails") and ticket_data["completionDetails"].get("completedAt"):
                completed_at = ticket_data["completionDetails"]["completedAt"]
                if isinstance(completed_at, datetime):
                    completed_date = completed_at
                else:
                    completed_date = completed_at.to_datetime() if hasattr(completed_at, 'to_datetime') else completed_at
                
                # Check if completed today
                if start_of_day <= completed_date <= end_of_day:
                    dealership_id = ticket_data.get("dealership")
                    if dealership_id in dealership_data:
                        cost = ticket_data.get("totalCost", 0.0)
                        dealership_data[dealership_id]["tickets"].append(ticket_data)
                        dealership_data[dealership_id]["ticket_revenue"] += cost
                        dealership_data[dealership_id]["ticket_count"] += 1
    except Exception as e:
        print(f"Error fetching tickets: {e}")
    
    # Fetch service data (washes, photos, lot prep) for each dealership
    for dealership_id in dealership_ids:
        try:
            # Service Washes
            wash_ref = firestore_db.collection(f"ServiceWash/{dealership_id}/{date_folder}")
            wash_docs = wash_ref.stream()
            for doc in wash_docs:
                wash_data = doc.to_dict()
                cost = wash_data.get("serviceWashCost", 0.0)
                dealership_data[dealership_id]["washes"].append(wash_data)
                dealership_data[dealership_id]["wash_revenue"] += cost
                dealership_data[dealership_id]["wash_count"] += 1
            
            # Photos
            photo_ref = firestore_db.collection(f"Photos/{dealership_id}/{date_folder}")
            photo_docs = photo_ref.stream()
            for doc in photo_docs:
                photo_data = doc.to_dict()
                cost = photo_data.get("photosCost", 0.0)
                dealership_data[dealership_id]["photos"].append(photo_data)
                dealership_data[dealership_id]["photo_revenue"] += cost
                dealership_data[dealership_id]["photo_count"] += 1
            
            # Lot Prep
            lot_prep_ref = firestore_db.collection(f"LotPrep/{dealership_id}/{date_folder}")
            lot_prep_docs = lot_prep_ref.stream()
            for doc in lot_prep_docs:
                lot_prep_data = doc.to_dict()
                cost = lot_prep_data.get("serviceWashCost", 0.0)  # Note: lot prep uses serviceWashCost field
                dealership_data[dealership_id]["lot_prep"].append(lot_prep_data)
                dealership_data[dealership_id]["lot_prep_revenue"] += cost
                dealership_data[dealership_id]["lot_prep_count"] += 1
                
        except Exception as e:
            print(f"Error fetching service data for {dealership_id}: {e}")
    
    return dealership_data

async def get_labor_costs_for_dealerships(dealership_ids: List[str]) -> Dict[str, float]:
    """Get today's labor costs for given dealerships using the existing labor API"""
    try:
        from core.firebase import auth as firebase_auth
        
        # This would typically use the admin user's token, but since we're internal, 
        # we can call the labor API directly or use the existing labor analytics
        
        # For now, we'll return a placeholder - in production you'd integrate with your labor API
        labor_costs = {}
        
        # You can integrate this with your existing labor analytics endpoints
        # by calling them internally or sharing the same logic
        
        for dealership_id in dealership_ids:
            labor_costs[dealership_id] = 0.0  # Placeholder
            
        return labor_costs
        
    except Exception as e:
        print(f"Error fetching labor costs: {e}")
        return {dealership_id: 0.0 for dealership_id in dealership_ids}

# --- API Endpoints ---

@router.get("/company-summary/today", response_model=CompanyWideSummary)
async def get_company_financial_summary_today(
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role)
):
    """Get today's complete financial summary for the entire company"""
    
    target_date = datetime.now(timezone.utc).date()
    
    # Get all dealerships
    try:
        dealership_names = await get_all_dealership_names()
        dealership_ids = list(dealership_names.keys())
        
        if not dealership_ids:
            raise HTTPException(status_code=404, detail="No dealerships found")
        
        # Fetch financial data
        dealership_data = await get_firestore_financial_data(dealership_ids, target_date)
        
        # Fetch labor costs
        labor_costs = await get_labor_costs_for_dealerships(dealership_ids)
        
        # Calculate company totals
        total_revenue = 0.0
        total_labor_cost = 0.0
        total_ticket_revenue = 0.0
        total_wash_revenue = 0.0
        total_photo_revenue = 0.0
        total_lot_prep_revenue = 0.0
        total_tickets = 0
        total_washes = 0
        total_photos = 0
        total_lot_preps = 0
        profitable_dealerships = 0
        
        for dealership_id, data in dealership_data.items():
            revenue = (data["ticket_revenue"] + data["wash_revenue"] + 
                      data["photo_revenue"] + data["lot_prep_revenue"])
            labor_cost = labor_costs.get(dealership_id, 0.0)
            
            total_revenue += revenue
            total_labor_cost += labor_cost
            total_ticket_revenue += data["ticket_revenue"]
            total_wash_revenue += data["wash_revenue"]
            total_photo_revenue += data["photo_revenue"]
            total_lot_prep_revenue += data["lot_prep_revenue"]
            total_tickets += data["ticket_count"]
            total_washes += data["wash_count"]
            total_photos += data["photo_count"]
            total_lot_preps += data["lot_prep_count"]
            
            if revenue > labor_cost:
                profitable_dealerships += 1
        
        total_profit_loss = total_revenue - total_labor_cost
        
        return CompanyWideSummary(
            analysis_date=target_date.isoformat(),
            analysis_timestamp=datetime.now(timezone.utc),
            total_revenue=total_revenue,
            total_labor_cost=total_labor_cost,
            total_profit_loss=total_profit_loss,
            total_ticket_revenue=total_ticket_revenue,
            total_wash_revenue=total_wash_revenue,
            total_photo_revenue=total_photo_revenue,
            total_lot_prep_revenue=total_lot_prep_revenue,
            total_tickets=total_tickets,
            total_washes=total_washes,
            total_photos=total_photos,
            total_lot_preps=total_lot_preps,
            dealership_count=len(dealership_ids),
            profitable_dealerships=profitable_dealerships
        )
        
    except Exception as e:
        print(f"Error in company financial summary: {e}")
        raise HTTPException(status_code=500, detail="Error calculating company financial summary")

@router.get("/dealership/{dealership_id}/summary", response_model=DealershipFinancialSummary)
async def get_dealership_financial_summary(
    dealership_id: str,
    target_date: Optional[date] = Query(None, description="Target date (YYYY-MM-DD), defaults to today"),
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role)
):
    """Get financial summary for a specific dealership"""
    
    if not target_date:
        target_date = datetime.now(timezone.utc).date()
    
    try:
        # Get dealership name
        dealership_name = await get_dealership_name(dealership_id)
        
        # Fetch financial data
        dealership_data = await get_firestore_financial_data([dealership_id], target_date)
        data = dealership_data.get(dealership_id, {})
        
        # Fetch labor cost
        labor_costs = await get_labor_costs_for_dealerships([dealership_id])
        labor_cost = labor_costs.get(dealership_id, 0.0)
        
        # Calculate totals
        total_revenue = (data.get("ticket_revenue", 0.0) + data.get("wash_revenue", 0.0) + 
                        data.get("photo_revenue", 0.0) + data.get("lot_prep_revenue", 0.0))
        profit_loss = total_revenue - labor_cost
        labor_percentage = (labor_cost / total_revenue * 100) if total_revenue > 0 else 0.0
        
        return DealershipFinancialSummary(
            dealership_id=dealership_id,
            dealership_name=dealership_name,
            ticket_revenue=data.get("ticket_revenue", 0.0),
            wash_revenue=data.get("wash_revenue", 0.0),
            photo_revenue=data.get("photo_revenue", 0.0),
            lot_prep_revenue=data.get("lot_prep_revenue", 0.0),
            total_revenue=total_revenue,
            ticket_count=data.get("ticket_count", 0),
            wash_count=data.get("wash_count", 0),
            photo_count=data.get("photo_count", 0),
            lot_prep_count=data.get("lot_prep_count", 0),
            labor_cost=labor_cost,
            profit_loss=profit_loss,
            labor_percentage=labor_percentage
        )
        
    except Exception as e:
        print(f"Error fetching dealership financial summary: {e}")
        raise HTTPException(status_code=500, detail="Error calculating dealership financial summary")

@router.get("/dealership/{dealership_id}/detailed-breakdown", response_model=DealershipDetailedBreakdown)
async def get_dealership_detailed_breakdown(
    dealership_id: str,
    target_date: Optional[date] = Query(None, description="Target date (YYYY-MM-DD), defaults to today"),
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role)
):
    """Get detailed service breakdown for a specific dealership"""
    
    if not target_date:
        target_date = datetime.now(timezone.utc).date()
    
    try:
        dealership_name = await get_dealership_name(dealership_id)
        dealership_data = await get_firestore_financial_data([dealership_id], target_date)
        data = dealership_data.get(dealership_id, {})
        labor_costs = await get_labor_costs_for_dealerships([dealership_id])
        labor_cost = labor_costs.get(dealership_id, 0.0)
        
        # Break down ticket services by type
        ticket_services = {}
        for ticket in data.get("tickets", []):
            service = ticket.get("service", "Unknown")
            if service not in ticket_services:
                ticket_services[service] = {"count": 0, "revenue": 0.0}
            ticket_services[service]["count"] += 1
            ticket_services[service]["revenue"] += ticket.get("totalCost", 0.0)
        
        ticket_service_breakdown = [
            ServiceBreakdown(service_type=service, count=stats["count"], revenue=stats["revenue"])
            for service, stats in ticket_services.items()
        ]
        
        # Create service breakdowns
        wash_breakdown = ServiceBreakdown(
            service_type="Service Washes",
            count=data.get("wash_count", 0),
            revenue=data.get("wash_revenue", 0.0)
        )
        
        photo_breakdown = ServiceBreakdown(
            service_type="Photos",
            count=data.get("photo_count", 0),
            revenue=data.get("photo_revenue", 0.0)
        )
        
        lot_prep_breakdown = ServiceBreakdown(
            service_type="Lot Prep",
            count=data.get("lot_prep_count", 0),
            revenue=data.get("lot_prep_revenue", 0.0)
        )
        
        total_revenue = (data.get("ticket_revenue", 0.0) + data.get("wash_revenue", 0.0) + 
                        data.get("photo_revenue", 0.0) + data.get("lot_prep_revenue", 0.0))
        total_count = (data.get("ticket_count", 0) + data.get("wash_count", 0) + 
                      data.get("photo_count", 0) + data.get("lot_prep_count", 0))
        profit_loss = total_revenue - labor_cost
        
        return DealershipDetailedBreakdown(
            dealership_id=dealership_id,
            dealership_name=dealership_name,
            ticket_services=ticket_service_breakdown,
            wash_breakdown=wash_breakdown,
            photo_breakdown=photo_breakdown,
            lot_prep_breakdown=lot_prep_breakdown,
            total_revenue=total_revenue,
            total_count=total_count,
            labor_cost=labor_cost,
            profit_loss=profit_loss
        )
        
    except Exception as e:
        print(f"Error fetching detailed breakdown: {e}")
        raise HTTPException(status_code=500, detail="Error calculating detailed breakdown")

@router.get("/all-dealerships/summary", response_model=List[DealershipFinancialSummary])
async def get_all_dealerships_financial_summary(
    target_date: Optional[date] = Query(None, description="Target date (YYYY-MM-DD), defaults to today"),
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role)
):
    """Get financial summary for all dealerships"""
    
    if not target_date:
        target_date = datetime.now(timezone.utc).date()
    
    try:
        dealership_names = await get_all_dealership_names()
        dealership_ids = list(dealership_names.keys())
        
        if not dealership_ids:
            return []
        
        dealership_data = await get_firestore_financial_data(dealership_ids, target_date)
        labor_costs = await get_labor_costs_for_dealerships(dealership_ids)
        
        summaries = []
        for dealership_id in dealership_ids:
            data = dealership_data.get(dealership_id, {})
            labor_cost = labor_costs.get(dealership_id, 0.0)
            
            total_revenue = (data.get("ticket_revenue", 0.0) + data.get("wash_revenue", 0.0) + 
                            data.get("photo_revenue", 0.0) + data.get("lot_prep_revenue", 0.0))
            profit_loss = total_revenue - labor_cost
            labor_percentage = (labor_cost / total_revenue * 100) if total_revenue > 0 else 0.0
            
            summaries.append(DealershipFinancialSummary(
                dealership_id=dealership_id,
                dealership_name=dealership_names.get(dealership_id, dealership_id),
                ticket_revenue=data.get("ticket_revenue", 0.0),
                wash_revenue=data.get("wash_revenue", 0.0),
                photo_revenue=data.get("photo_revenue", 0.0),
                lot_prep_revenue=data.get("lot_prep_revenue", 0.0),
                total_revenue=total_revenue,
                ticket_count=data.get("ticket_count", 0),
                wash_count=data.get("wash_count", 0),
                photo_count=data.get("photo_count", 0),
                lot_prep_count=data.get("lot_prep_count", 0),
                labor_cost=labor_cost,
                profit_loss=profit_loss,
                labor_percentage=labor_percentage
            ))
        
        # Sort by total revenue descending
        summaries.sort(key=lambda x: x.total_revenue, reverse=True)
        return summaries
        
    except Exception as e:
        print(f"Error fetching all dealership summaries: {e}")
        raise HTTPException(status_code=500, detail="Error calculating dealership summaries")

@router.get("/date-range/summary", response_model=DateRangeFinancialSummary)
async def get_date_range_financial_summary(
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role)
):
    """Get financial summary for a date range"""
    
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="Start date cannot be after end date")
    
    if (end_date - start_date).days > 90:
        raise HTTPException(status_code=400, detail="Date range cannot exceed 90 days")
    
    try:
        dealership_names = await get_all_dealership_names()
        dealership_ids = list(dealership_names.keys())
        
        # Calculate totals across date range
        total_revenue = 0.0
        total_labor_cost = 0.0
        dealership_totals = defaultdict(lambda: {
            "ticket_revenue": 0.0, "wash_revenue": 0.0, "photo_revenue": 0.0, "lot_prep_revenue": 0.0,
            "ticket_count": 0, "wash_count": 0, "photo_count": 0, "lot_prep_count": 0,
            "labor_cost": 0.0
        })
        
        # Iterate through each date in range
        current_date = start_date
        date_count = 0
        
        while current_date <= end_date:
            date_count += 1
            
            # Fetch data for this date
            daily_data = await get_firestore_financial_data(dealership_ids, current_date)
            daily_labor = await get_labor_costs_for_dealerships(dealership_ids)
            
            # Accumulate totals
            for dealership_id, data in daily_data.items():
                dealership_totals[dealership_id]["ticket_revenue"] += data.get("ticket_revenue", 0.0)
                dealership_totals[dealership_id]["wash_revenue"] += data.get("wash_revenue", 0.0)
                dealership_totals[dealership_id]["photo_revenue"] += data.get("photo_revenue", 0.0)
                dealership_totals[dealership_id]["lot_prep_revenue"] += data.get("lot_prep_revenue", 0.0)
                dealership_totals[dealership_id]["ticket_count"] += data.get("ticket_count", 0)
                dealership_totals[dealership_id]["wash_count"] += data.get("wash_count", 0)
                dealership_totals[dealership_id]["photo_count"] += data.get("photo_count", 0)
                dealership_totals[dealership_id]["lot_prep_count"] += data.get("lot_prep_count", 0)
                dealership_totals[dealership_id]["labor_cost"] += daily_labor.get(dealership_id, 0.0)
            
            current_date += timedelta(days=1)
        
        # Calculate company totals and dealership summaries
        dealership_summaries = []
        
        for dealership_id, totals in dealership_totals.items():
            revenue = (totals["ticket_revenue"] + totals["wash_revenue"] + 
                      totals["photo_revenue"] + totals["lot_prep_revenue"])
            labor_cost = totals["labor_cost"]
            profit_loss = revenue - labor_cost
            labor_percentage = (labor_cost / revenue * 100) if revenue > 0 else 0.0
            
            total_revenue += revenue
            total_labor_cost += labor_cost
            
            dealership_summaries.append(DealershipFinancialSummary(
                dealership_id=dealership_id,
                dealership_name=dealership_names.get(dealership_id, dealership_id),
                ticket_revenue=totals["ticket_revenue"],
                wash_revenue=totals["wash_revenue"],
                photo_revenue=totals["photo_revenue"],
                lot_prep_revenue=totals["lot_prep_revenue"],
                total_revenue=revenue,
                ticket_count=totals["ticket_count"],
                wash_count=totals["wash_count"],
                photo_count=totals["photo_count"],
                lot_prep_count=totals["lot_prep_count"],
                labor_cost=labor_cost,
                profit_loss=profit_loss,
                labor_percentage=labor_percentage
            ))
        
        total_profit_loss = total_revenue - total_labor_cost
        
        # Calculate daily averages
        avg_daily_revenue = total_revenue / date_count if date_count > 0 else 0.0
        avg_daily_labor_cost = total_labor_cost / date_count if date_count > 0 else 0.0
        avg_daily_profit = total_profit_loss / date_count if date_count > 0 else 0.0
        
        return DateRangeFinancialSummary(
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            date_range_days=date_count,
            total_revenue=total_revenue,
            total_labor_cost=total_labor_cost,
            total_profit_loss=total_profit_loss,
            avg_daily_revenue=avg_daily_revenue,
            avg_daily_labor_cost=avg_daily_labor_cost,
            avg_daily_profit=avg_daily_profit,
            dealership_summaries=dealership_summaries
        )
        
    except Exception as e:
        print(f"Error calculating date range summary: {e}")
        raise HTTPException(status_code=500, detail="Error calculating date range financial summary")

@router.get("/top-performers/today", response_model=TopPerformersResponse)
async def get_top_performers_today(
    limit: int = Query(5, description="Number of top performers to return"),
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role)
):
    """Get top performing dealerships by various metrics for today"""
    
    target_date = datetime.now(timezone.utc).date()
    
    try:
        # Get all dealership summaries
        summaries = await get_all_dealerships_financial_summary(target_date, session, admin)
        
        # Sort by different metrics
        top_revenue = sorted(summaries, key=lambda x: x.total_revenue, reverse=True)[:limit]
        top_profit = sorted(summaries, key=lambda x: x.profit_loss, reverse=True)[:limit]
        
        # Top by volume (total count of all services)
        for summary in summaries:
            summary.total_volume = (summary.ticket_count + summary.wash_count + 
                                   summary.photo_count + summary.lot_prep_count)
        top_volume = sorted(summaries, key=lambda x: getattr(x, 'total_volume', 0), reverse=True)[:limit]
        
        return TopPerformersResponse(
            analysis_date=target_date.isoformat(),
            top_revenue_dealerships=top_revenue,
            top_profit_dealerships=top_profit,
            top_volume_dealerships=top_volume
        )
        
    except Exception as e:
        print(f"Error getting top performers: {e}")
        raise HTTPException(status_code=500, detail="Error calculating top performers")

@router.get("/revenue-only/company-total/today")
async def get_company_revenue_total_today(
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role)
):
    """Quick endpoint to get just the total company revenue for today"""
    
    try:
        summary = await get_company_financial_summary_today(session, admin)
        return {
            "date": summary.analysis_date,
            "total_revenue": summary.total_revenue,
            "timestamp": summary.analysis_timestamp
        }
    except Exception as e:
        print(f"Error getting company revenue total: {e}")
        raise HTTPException(status_code=500, detail="Error calculating company revenue total")

@router.get("/profit-only/company-total/today")
async def get_company_profit_total_today(
    session: Session = Depends(get_session),
    admin: dict = Depends(require_admin_role)
):
    """Quick endpoint to get just the total company profit for today"""
    
    try:
        summary = await get_company_financial_summary_today(session, admin)
        return {
            "date": summary.analysis_date,
            "total_profit_loss": summary.total_profit_loss,
            "total_revenue": summary.total_revenue,
            "total_labor_cost": summary.total_labor_cost,
            "is_profitable": summary.total_profit_loss > 0,
            "timestamp": summary.analysis_timestamp
        }
    except Exception as e:
        print(f"Error getting company profit total: {e}")
        raise HTTPException(status_code=500, detail="Error calculating company profit total") 