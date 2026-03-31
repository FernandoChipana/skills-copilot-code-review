"""
Endpoints for managing school announcements.
"""

from datetime import date, datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from bson import ObjectId

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


def _parse_date(value: str, field_name: str) -> date:
    """Parse an ISO date string and raise a clear validation error when invalid."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field_name} must use YYYY-MM-DD format"
        ) from exc


def _ensure_teacher(username: Optional[str]) -> Dict[str, Any]:
    """Validate that a teacher username exists before allowing protected actions."""
    if not username:
        raise HTTPException(status_code=401, detail="Authentication required for this action")

    teacher = teachers_collection.find_one({"_id": username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


def _serialize_announcement(document: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize MongoDB documents for API responses."""
    return {
        "id": str(document["_id"]),
        "message": document["message"],
        "start_date": document.get("start_date"),
        "end_date": document["end_date"],
        "created_at": document.get("created_at"),
        "updated_at": document.get("updated_at")
    }


@router.get("", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get currently active announcements for the public banner."""
    today = date.today().isoformat()

    query = {
        "end_date": {"$gte": today},
        "$or": [
            {"start_date": {"$exists": False}},
            {"start_date": None},
            {"start_date": {"$lte": today}}
        ]
    }

    announcements = announcements_collection.find(query).sort("end_date", 1)
    return [_serialize_announcement(item) for item in announcements]


@router.get("/all", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get all announcements for management views (requires authentication)."""
    _ensure_teacher(teacher_username)

    announcements = announcements_collection.find({}).sort("created_at", -1)
    return [_serialize_announcement(item) for item in announcements]


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    message: str,
    end_date: str,
    start_date: Optional[str] = None,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create a new announcement (requires authentication)."""
    _ensure_teacher(teacher_username)

    normalized_message = message.strip()
    if not normalized_message:
        raise HTTPException(status_code=400, detail="message is required")

    parsed_end_date = _parse_date(end_date, "end_date")
    parsed_start_date: Optional[date] = None
    if start_date:
        parsed_start_date = _parse_date(start_date, "start_date")

    if parsed_start_date and parsed_start_date > parsed_end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")

    now = datetime.utcnow().isoformat()
    document = {
        "message": normalized_message,
        "end_date": parsed_end_date.isoformat(),
        "created_at": now,
        "updated_at": now
    }

    if parsed_start_date:
        document["start_date"] = parsed_start_date.isoformat()

    result = announcements_collection.insert_one(document)
    created = announcements_collection.find_one({"_id": result.inserted_id})

    return _serialize_announcement(created)


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    message: str,
    end_date: str,
    start_date: Optional[str] = None,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement (requires authentication)."""
    _ensure_teacher(teacher_username)

    try:
        object_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    existing = announcements_collection.find_one({"_id": object_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    normalized_message = message.strip()
    if not normalized_message:
        raise HTTPException(status_code=400, detail="message is required")

    parsed_end_date = _parse_date(end_date, "end_date")
    parsed_start_date: Optional[date] = None
    if start_date:
        parsed_start_date = _parse_date(start_date, "start_date")

    if parsed_start_date and parsed_start_date > parsed_end_date:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")

    update_fields: Dict[str, Any] = {
        "message": normalized_message,
        "end_date": parsed_end_date.isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

    if parsed_start_date:
        update_fields["start_date"] = parsed_start_date.isoformat()
    else:
        update_fields["start_date"] = None

    announcements_collection.update_one({"_id": object_id}, {"$set": update_fields})
    updated = announcements_collection.find_one({"_id": object_id})

    return _serialize_announcement(updated)


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, str]:
    """Delete an announcement (requires authentication)."""
    _ensure_teacher(teacher_username)

    try:
        object_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    result = announcements_collection.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted successfully"}
