
from flask import Blueprint, jsonify, render_template, request

from .utils.database import Database
from .utils.llm import (
    extract_update,
    find_requested_points,
    _normalize_search_text,
    _point_name_matches_query,
    normalize_arabic,
    service_matches,
    synthesize_response,
    understand_request,
)

main = Blueprint("main", __name__)
db = Database()


@main.get("/")
def index():
    return render_template("index.html")


@main.get("/owner")
def owner():
    return render_template("owner.html")


@main.get("/api/chargepoints")
def chargepoints():
    query = request.args.get("q", "").strip()
    rows = db.search_chargepoints(query) if query else db.get_chargepoints()
    return jsonify(rows)


@main.get("/api/chargepoints/semantic-search")
def semantic_search():
    query = request.args.get("q", "").strip()
    return jsonify(db.semantic_search(query) if query else [])



@main.post("/api/smart-search")
def smart_search():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("message", "")).strip()

    if not text:
        return jsonify({
            "error": "اكتب طلب البحث أولًا"
        }), 400

    intent = understand_request(db, text)

    all_points = db.get_chargepoints()
    points = list(all_points)

    normalized_text = _normalize_search_text(text)
    area = intent.get("area")
    service = intent.get("service")

    exact_points = [
        point
        for point in all_points
        if _normalize_search_text(
            str(point.get("chargepoint_name", ""))
        ) in normalized_text
    ]

    requested_points = exact_points or [
        point
        for point in all_points
        if _point_name_matches_query(
            str(point.get("chargepoint_name", "")),
            normalized_text,
        )
    ]

    named_point_search = bool(requested_points)

    if named_point_search:
        points = requested_points

    else:
        if area:
            normalized_area = _normalize_search_text(area)

            points = [
                point
                for point in points
                if normalized_area in _normalize_search_text(
                    str(point.get("area", ""))
                )
            ]

        if service:
            points = [
                point
                for point in points
                if service_matches(
                    service,
                    str(point.get("service_type", "")),
                )
            ]

    wants_open = any(
        phrase in normalized_text
        for phrase in [
            "مفتوح",
            "مفتوحه",
            "مفتوحة",
            "متاح",
            "متاحه",
            "متاحة",
            "شغال",
            "شغاله",
            "شغالة",
            "شغالين",
        ]
    )

    wants_not_full = any(
        phrase in normalized_text
        for phrase in [
            "مش مليانه",
            "مش مليئة",
            "غير مليانه",
            "غير ممتلئه",
            "غير ممتلئ",
            "فيها مكان",
            "في مكان",
            "مكان فاضي",
            "مكان شاغر",
            "مش فل",
            "مش full",
            "مش ممتلئه",
            "فاضيه",
            "فاضي",
        ]
    )

    if not named_point_search and (wants_open or wants_not_full):
        points = [
            point
            for point in points
            if str(point.get("status", "")).strip().lower()
            == "open"
        ]

    if not named_point_search and wants_not_full:
        points = [
            point
            for point in points
            if int(point.get("waiting_count") or 0)
            < int(point.get("capacity") or 0)
        ]

    if intent.get("waiting_preference") == "low":
        if not named_point_search:
            points = [
                point
                for point in points
                if str(point.get("status", "")).strip().lower()
                == "open"
                and int(point.get("waiting_count") or 0) <= 3
            ]

        points.sort(
            key=lambda point: int(
                point.get("waiting_count") or 0
            )
        )

    return jsonify({
        "intent": intent,
        "points": points,
        "reply": synthesize_response(
            db,
            text,
            points,
        ),
    })



@main.post("/api/owner/login")
def owner_login():
    payload = request.get_json(silent=True) or {}
    owner = db.get_owner_by_key(str(payload.get("owner_key", "")).strip())
    if not owner:
        return jsonify({"error": "رمز المالك غير صحيح"}), 401
    return jsonify(owner)


@main.get("/api/owners/<int:owner_id>/chargepoints")
def owner_chargepoints(owner_id: int):
    return jsonify(db.get_chargepoints(owner_id))


@main.put("/api/chargepoints/<int:chargepoint_id>")
def update_chargepoint(chargepoint_id: int):
    payload = request.get_json(silent=True) or {}
    point = db.update_chargepoint(chargepoint_id, payload)
    if not point:
        return jsonify({"error": "نقطة الشحن غير موجودة"}), 404
    return jsonify(point)


@main.post("/api/owner/extract-update")
def owner_extract_update():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"error": "أدخل رسالة المالك"}), 400
    return jsonify(extract_update(db, message))
