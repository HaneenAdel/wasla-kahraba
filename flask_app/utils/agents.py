"""Course-style experts and orchestrator for charging-point workflows."""
from __future__ import annotations

from typing import Any

from .llm import (
    _normalize_search_text,
    _point_name_matches_query,
    normalize_arabic,
    service_matches,
    synthesize_response,
    understand_request,
)


class DatabaseReadExpert:
    """Reads and filters charging points using the structured user intent."""

    def __init__(self, database):
        self.database = database

    def search(self, text: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        intent = understand_request(self.database, text)
        all_points = self.database.get_chargepoints()
        normalized_text = _normalize_search_text(text)
        area = intent.get("area")
        service = intent.get("service")

        exact_points = [
            point for point in all_points
            if _normalize_search_text(str(point.get("chargepoint_name", ""))) in normalized_text
        ]
        requested_points = exact_points or [
            point for point in all_points
            if _point_name_matches_query(str(point.get("chargepoint_name", "")), normalized_text)
        ]
        named_point_search = bool(exact_points) or (bool(requested_points) and not area)
        points = requested_points if named_point_search else list(all_points)

        if not named_point_search and area:
            normalized_area = _normalize_search_text(area)
            points = [
                point for point in points
                if normalized_area in _normalize_search_text(str(point.get("area", "")))
            ]
        if not named_point_search and service:
            points = [
                point for point in points
                if service_matches(service, str(point.get("service_type", "")))
            ]

        normalized_status_text = normalize_arabic(text)
        wants_open = any(word in normalized_text for word in (
            "مفتوح", "مفتوحه", "مفتوحة", "متاح", "متاحه", "متاحة",
            "شغال", "شغاله", "شغالة", "شغالين", "open",
        ))
        wants_full = any(word in normalized_status_text for word in (
            "ممتلئ", "ممتلئه", "ممتلئة", "مليان", "مليانه", "full",
        ))
        wants_closed = any(word in normalized_text for word in (
            "مغلق", "مغلقة", "مقفول", "مسكر", "closed",
        ))
        wants_not_full = any(phrase in normalized_status_text for phrase in (
            "مش مليان", "مش مليانه", "مش مليئة", "غير مليان", "غير مليانه", "غير ممتلئه", "غير ممتلئ",
            "فيها مكان", "في مكان", "مكان فاضي", "مكان شاغر", "مش فل",
            "مش full", "مش ممتلئه", "فاضيه", "فاضي",
        ))
        wants_full = wants_full and not wants_not_full
        asks_group_availability = (
            not exact_points
            and len(requested_points) > 1
            and any(word in normalized_text for word in ("متاح", "متاحه", "متاحة"))
            and not any(word in normalized_text for word in ("مفتوح", "مفتوحه", "مفتوحة", "open"))
        )

        if wants_open and not asks_group_availability:
            points = [point for point in points if str(point.get("status", "")).lower() == "open"]
        if wants_full:
            points = [point for point in points if str(point.get("status", "")).lower() == "full"]
        if wants_closed:
            points = [point for point in points if str(point.get("status", "")).lower() == "closed"]
        if not named_point_search and wants_not_full:
            points = [
                point for point in points
                if str(point.get("status", "")).lower() not in {"full", "closed"}
                and int(point.get("waiting_count") or 0) < 3
            ]
        if intent.get("waiting_preference") == "low" and not named_point_search:
            points = [
                point for point in points
                if str(point.get("status", "")).lower() == "open"
                and int(point.get("waiting_count") or 0) <= 3
            ]
            points.sort(key=lambda point: int(point.get("waiting_count") or 0))

        return intent, points


class SemanticSearchExpert:
    """Ranks points by embedding similarity when the user asks semantically."""

    def __init__(self, database):
        self.database = database

    def search(self, text: str) -> list[dict[str, Any]]:
        return self.database.semantic_search(text)


class DatabaseWriteExpert:
    """Performs owner-authorized updates and deletions."""

    def __init__(self, database):
        self.database = database

    def update(self, chargepoint_id: int, owner_id: int, data: dict[str, Any]):
        return self.database.update_chargepoint_for_owner(chargepoint_id, owner_id, data)

    def delete(self, chargepoint_id: int, owner_id: int):
        return self.database.delete_chargepoint_for_owner(chargepoint_id, owner_id)


class Orchestrator:
    """Chooses the expert responsible for each user operation."""

    def __init__(self, database):
        self.read_expert = DatabaseReadExpert(database)
        self.semantic_search_expert = SemanticSearchExpert(database)
        self.write_expert = DatabaseWriteExpert(database)
        self.database = database

    def search(self, text: str) -> dict[str, Any]:
        intent, points = self.read_expert.search(text)
        return {
            "intent": intent,
            "points": points,
            "reply": synthesize_response(self.database, text, points, intent),
        }

    def semantic_search(self, text: str) -> list[dict[str, Any]]:
        return self.semantic_search_expert.search(text)


orchestrator = Orchestrator
