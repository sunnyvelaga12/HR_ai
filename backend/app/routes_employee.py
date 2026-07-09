"""
Employee Management API Routes

Provides endpoints for:
- Employee profiles and data
- Attendance tracking
- Leave management
- Employee statistics
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timedelta
from typing import List
from sqlalchemy.orm import Session

from app.schemas import (
    EmployeeProfileResponse,
    LeaveBalanceResponse,
    AttendanceRecordResponse,
    EmployeeStatsResponse,
    LeaveStatsResponse,
)
from app.deps import get_current_user
from app.db import get_db

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])


# ─── Employee Profile ────────────────────────────────────────────────────────

@router.get("/profile/{employee_id}", response_model=EmployeeProfileResponse)
async def get_employee_profile(
    employee_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get complete employee profile with all details."""
    try:
        # TODO: Implement actual database query
        # For now, return sample data structure
        return {
            "employee_id": employee_id,
            "first_name": "John",
            "last_name": "Doe",
            "email": f"john.doe+{employee_id}@company.com",
            "phone": "+1-234-567-8900",
            "department": "Engineering",
            "designation": "Senior Software Engineer",
            "manager_name": "Jane Smith",
            "office_location": "San Francisco",
            "work_mode": "Hybrid",
            "employment_status": "Active",
            "years_with_company": 4,
            "performance_rating": 4.5,
            "skills": ["Python", "AWS", "Docker", "Kubernetes"],
            "certifications": ["AWS Solutions Architect", "CKA"],
            "date_of_joining": "2020-01-15",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching profile: {str(e)}")


@router.get("/profile/me", response_model=EmployeeProfileResponse)
async def get_my_profile(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get current user's employee profile."""
    try:
        return {
            "employee_id": current_user.get("employee_id", "EMP001"),
            "first_name": current_user.get("first_name", "John"),
            "last_name": current_user.get("last_name", "Doe"),
            "email": current_user.get("email", "john.doe@company.com"),
            "phone": "+1-234-567-8900",
            "department": "Engineering",
            "designation": "Senior Software Engineer",
            "manager_name": "Jane Smith",
            "office_location": "San Francisco",
            "work_mode": "Hybrid",
            "employment_status": "Active",
            "years_with_company": 4,
            "performance_rating": 4.5,
            "skills": ["Python", "AWS", "Docker", "Kubernetes"],
            "certifications": ["AWS Solutions Architect", "CKA"],
            "date_of_joining": "2020-01-15",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching profile: {str(e)}")


# ─── Leave Balance ────────────────────────────────────────────────────────────

@router.get("/leave-balance/{employee_id}", response_model=LeaveBalanceResponse)
async def get_leave_balance(
    employee_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get employee's leave balance."""
    try:
        return {
            "employee_id": employee_id,
            "casual_leave_total": 12,
            "casual_leave_used": 3,
            "casual_leave_remaining": 9,
            "sick_leave_total": 10,
            "sick_leave_used": 2,
            "sick_leave_remaining": 8,
            "privilege_leave_total": 20,
            "privilege_leave_used": 5,
            "privilege_leave_remaining": 15,
            "floating_holidays_total": 5,
            "floating_holidays_used": 2,
            "floating_holidays_remaining": 3,
            "last_updated": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching leave balance: {str(e)}")


@router.get("/leave-balance/me", response_model=LeaveBalanceResponse)
async def get_my_leave_balance(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get current user's leave balance."""
    employee_id = current_user.get("employee_id", "EMP001")
    try:
        return {
            "employee_id": employee_id,
            "casual_leave_total": 12,
            "casual_leave_used": 3,
            "casual_leave_remaining": 9,
            "sick_leave_total": 10,
            "sick_leave_used": 2,
            "sick_leave_remaining": 8,
            "privilege_leave_total": 20,
            "privilege_leave_used": 5,
            "privilege_leave_remaining": 15,
            "floating_holidays_total": 5,
            "floating_holidays_used": 2,
            "floating_holidays_remaining": 3,
            "last_updated": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching leave balance: {str(e)}")


# ─── Attendance ──────────────────────────────────────────────────────────────

@router.get("/attendance/{employee_id}", response_model=List[AttendanceRecordResponse])
async def get_attendance(
    employee_id: str,
    days: int = Query(5, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get employee's attendance records for past N days."""
    try:
        records = []
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            records.append({
                "date": date.strftime("%Y-%m-%d"),
                "status": ["Present", "WFH", "Half-Day", "Absent", "Leave"][i % 5],
                "hours_worked": 8.5 if i % 2 == 0 else 4.0,
                "check_in_time": "09:00 AM",
                "check_out_time": "05:30 PM",
                "location": "San Francisco" if i % 2 == 0 else "Remote",
            })
        return sorted(records, key=lambda x: x["date"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching attendance: {str(e)}")


@router.get("/attendance/me", response_model=List[AttendanceRecordResponse])
async def get_my_attendance(
    days: int = Query(5, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get current user's attendance records."""
    employee_id = current_user.get("employee_id", "EMP001")
    try:
        records = []
        for i in range(days):
            date = datetime.now() - timedelta(days=i)
            records.append({
                "date": date.strftime("%Y-%m-%d"),
                "status": ["Present", "WFH", "Half-Day", "Absent", "Leave"][i % 5],
                "hours_worked": 8.5 if i % 2 == 0 else 4.0,
                "check_in_time": "09:00 AM",
                "check_out_time": "05:30 PM",
                "location": "San Francisco" if i % 2 == 0 else "Remote",
            })
        return sorted(records, key=lambda x: x["date"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching attendance: {str(e)}")


# ─── Employee Statistics ─────────────────────────────────────────────────────

@router.get("/stats", response_model=EmployeeStatsResponse)
async def get_employee_stats(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get company-wide employee statistics."""
    try:
        return {
            "total_employees": 125,
            "active_employees": 120,
            "on_leave_today": 12,
            "absent_today": 15,
            "present_today": 98,
            "work_from_home_today": 35,
            "terminations_this_month": 1,
            "new_hires_this_month": 3,
            "average_performance_rating": 4.2,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {str(e)}")


@router.get("/leave-stats", response_model=LeaveStatsResponse)
async def get_leave_stats(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get leave statistics."""
    try:
        return {
            "pending_approvals": 12,
            "approved_this_month": 28,
            "rejected_this_month": 2,
            "on_leave_today": 12,
            "returning_tomorrow": 5,
            "total_leaves_taken_this_year": 45,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching leave stats: {str(e)}")


# ─── Dashboard Data ──────────────────────────────────────────────────────────

@router.get("/dashboard-overview")
async def get_dashboard_overview(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Get all data needed for dashboard overview in one call."""
    try:
        employee_id = current_user.get("employee_id", "EMP001")
        
        profile = {
            "employee_id": employee_id,
            "first_name": "John",
            "last_name": "Doe",
            "department": "Engineering",
            "designation": "Senior Software Engineer",
            "manager_name": "Jane Smith",
            "performance_rating": 4.5,
        }
        
        leave_balance = {
            "casual_leave_remaining": 9,
            "sick_leave_remaining": 8,
            "privilege_leave_remaining": 15,
            "floating_holidays_remaining": 3,
        }
        
        attendance = []
        for i in range(5):
            date = datetime.now() - timedelta(days=i)
            attendance.append({
                "date": date.strftime("%Y-%m-%d"),
                "status": ["Present", "WFH", "Half-Day", "Absent", "Leave"][i % 5],
                "hours_worked": 8.5 if i % 2 == 0 else 4.0,
            })
        
        return {
            "profile": profile,
            "leave_balance": leave_balance,
            "attendance": sorted(attendance, key=lambda x: x["date"]),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching dashboard data: {str(e)}")
