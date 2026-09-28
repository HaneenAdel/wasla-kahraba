
import re
from datetime import datetime

from flask import Blueprint, jsonify, render_template, request, session

from .utils.database import Database
from .utils.agents import Orchestrator
from .utils.llm import _normalize_search_text, extract_update, service_matches

main = Blueprint("main", __name__)
db = Database()
agent_orchestrator = Orchestrator(db)


def _casefold_text(value: str) -> str:
    return _normalize_search_text(str(value or ""))


def _name_match(point_name: str, query: str) -> bool:
    normalized_point = _casefold_text(point_name)
    normalized_query = _casefold_text(query)
    if not normalized_point or not normalized_query:
        return False
    return normalized_query in normalized_point or normalized_point in normalized_query


def _extract_name_from_message(message: str) -> str:
    cleaned = re.sub(r"^(?:أضف|اضف|إضافة|اضافة|add|create|new|أنشئ|انشئ|إنشئ)\s*(?:نقطة\s*شحن\s*)?", "", message, flags=re.IGNORECASE)
    cleaned = re.split(r"\s+(?:في|ب|in|at)\s+", cleaned, maxsplit=1)[0]
    cleaned = cleaned.strip(" \t\n\r\-:;,.\"")
    return cleaned or "نقطة شحن جديدة"


def _extract_area_from_message(message: str) -> str:
    normalized = _casefold_text(message)
    area_map = {
        "المنطقة الوسطى": ["المنطقة الوسطى", "المنطقه الوسطى", "المحافظة الوسطى", "المحافظه الوسطى", "الوسطى", "الوسط"],
        "المنطقة الشمالية": ["المنطقة الشمالية", "المنطقه الشمالية", "الشمالية", "الشمال"],
        "المنطقة الغربية": ["المنطقة الغربية", "المنطقه الغربية", "الغربية", "الغرب"],
        "المنطقة الشرقية": ["المنطقة الشرقية", "المنطقه الشرقية", "الشرقية", "الشرق"],
    }
    for area_name, aliases in area_map.items():
        for alias in aliases:
            if _casefold_text(alias) in normalized:
                return area_name
    return "غير محدد"


def _extract_service_from_message(message: str) -> str:
    services = _extract_requested_services(message)
    return "، ".join(services) if services else "شحن هاتف"


def _extract_requested_services(message: str) -> list[str]:
    normalized = _casefold_text(message)
    services = []
    if any(term in normalized for term in ("لابتوب", "لاب توب", "laptop", "كمبيوتر محمول", "حاسوب محمول")):
        services.append("شحن لابتوب")
    if any(term in normalized for term in ("طبي", "جهاز طبي", "medical")):
        services.append("شحن جهاز طبي صغير")
    if any(term in normalized for term in (
        "هاتف", "هواتف", "موبايل", "موبايلات", "جوال", "جوالات", "mobile", "phone",
    )):
        services.append("شحن هاتف")
    return services


def _extract_status_from_message(message: str) -> str:
    normalized = _casefold_text(message)
    if any(term in normalized for term in ("مغلقة", "مغلق", "مسكر", "closed")):
        return "closed"
    if any(term in normalized for term in ("ممتلئة", "ممتلئ", "milyan", "full")):
        return "full"
    return "open"


def _extract_numeric_value(message: str, preferred_names: tuple[str, ...]) -> int:
    for name in preferred_names:
        match = re.search(rf"{re.escape(name)}\s*(\d+)", message)
        if match:
            return int(match.group(1))
    match = re.search(r"(\d+)", message)
    return int(match.group(1)) if match else 0


def _pending_action_reply(pending: dict[str, object]) -> str:
    action = pending.get("action")
    name = pending.get("chargepoint_name") or "النقطة"
    if action == "delete":
        return f"هل أنت متأكد من حذف «{name}»؟ اكتب «نعم» أو «إلغاء»."
    if action == "add":
        return f"هل تريد إضافة نقطة الشحن «{name}»؟ اكتب «نعم» أو «إلغاء»."
    if action == "update":
        return f"هل تريد تحديث بيانات «{name}»؟ اكتب «نعم» أو «إلغاء»."
    return "هل أنت متأكد؟ اكتب «نعم» أو «إلغاء»."


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
    return jsonify(agent_orchestrator.semantic_search(query) if query else [])



@main.post("/api/smart-search")
def smart_search():
    payload = request.get_json(silent=True) or {}
    text = str(payload.get("message", "")).strip()

    if not text:
        return jsonify({
            "error": "اكتب طلب البحث أولًا"
        }), 400

    normalized_text = _casefold_text(text)
    owner_action_keywords = (
        "احذف", "حذف", "شيل", "إزالة", "ازالة", "remove", "delete",
        "تعديل", "عدل", "تحديث", "اجعل", "خلي", "تقبل", "يدعم", "update", "edit",
        "اضافة", "إضافة", "أضف", "اضف", "add", "create", "new",
        "نعم", "yes", "إلغاء", "الغاء", "no"
    )

    if session.get("owner_id") and (
        session.get("pending_owner_action")
        or any(word in normalized_text for word in owner_action_keywords)
    ):
        return owner_assistant()

    result = agent_orchestrator.search(text)
    return jsonify(result)



@main.post("/api/owner/login")
def owner_login():
    payload = request.get_json(silent=True) or {}
    owner = db.get_owner_by_key(str(payload.get("owner_key", "")).strip())
    if not owner:
        return jsonify({"error": "رمز المالك غير صحيح"}), 401
    session["owner_id"] = owner["owner_id"]
    session.pop("pending_owner_action", None)
    return jsonify(owner)


@main.post("/api/owner/logout")
def owner_logout():
    session.pop("owner_id", None)
    session.pop("pending_owner_action", None)
    return jsonify({"logged_out": True})


@main.get("/api/owner/session")
def owner_session():
    owner_id = session.get("owner_id")
    owner = db.get_owner(owner_id) if owner_id else None
    if not owner:
        return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "owner_id": owner["owner_id"], "name": owner["name"]})


@main.get("/api/owners/<int:owner_id>/chargepoints")
def owner_chargepoints(owner_id: int):
    if session.get("owner_id") != owner_id:
        return jsonify({"error": "يجب تسجيل الدخول كمالك هذه النقاط"}), 403
    return jsonify(db.get_chargepoints(owner_id))


@main.put("/api/chargepoints/<int:chargepoint_id>")
def update_chargepoint(chargepoint_id: int):
    payload = request.get_json(silent=True) or {}
    owner_id = session.get("owner_id")
    if not owner_id:
        return jsonify({"error": "يجب تسجيل دخول المالك أولًا"}), 401
    point = agent_orchestrator.write_expert.update(chargepoint_id, owner_id, payload)
    if not point:
        return jsonify({"error": "نقطة الشحن غير موجودة أو لا تملك صلاحية تعديلها"}), 404
    return jsonify(point)


@main.delete("/api/chargepoints/<int:chargepoint_id>")
def delete_chargepoint(chargepoint_id: int):
    owner_id = session.get("owner_id")
    if not owner_id:
        return jsonify({"error": "يجب تسجيل دخول المالك أولًا"}), 401
    if not agent_orchestrator.write_expert.delete(chargepoint_id, owner_id):
        return jsonify({"error": "نقطة الشحن غير موجودة أو لا تملك صلاحية حذفها"}), 404
    return jsonify({"deleted": True, "chargepoint_id": chargepoint_id})


@main.post("/api/owner/assistant")
def owner_assistant():
    owner_id = session.get("owner_id")
    if not owner_id:
        return jsonify({"error": "يجب تسجيل دخول المالك أولًا"}), 401

    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"error": "اكتب طلبك أولًا"}), 400

    pending = session.get("pending_owner_action")
    normalized = _casefold_text(message)
    if pending:
        if normalized in {"نعم", "نعمًا", "yes", "y"}:
            action = pending.get("action")
            session.pop("pending_owner_action", None)
            if action == "delete":
                deleted = agent_orchestrator.write_expert.delete(
                    int(pending["chargepoint_id"]), owner_id
                )
                if not deleted:
                    return jsonify({"reply": "تعذر تنفيذ الحذف أو لم تعد النقطة مملوكة لك."})
                return jsonify({"reply": f"تم حذف نقطة الشحن: {pending['chargepoint_name']}"})
            if action == "add":
                created = db.add_chargepoint_for_owner(owner_id, pending.get("data", {}))
                if not created:
                    return jsonify({"reply": "تعذر إنشاء نقطة الشحن."})
                return jsonify({"reply": f"تمت إضافة نقطة الشحن: {created['chargepoint_name']}"})
            if action == "update":
                updated = agent_orchestrator.write_expert.update(
                    int(pending["chargepoint_id"]), owner_id, pending.get("data", {})
                )
                if not updated:
                    return jsonify({"reply": "تعذر تحديث هذه النقطة أو لم تعد مملوكة لك."})
                return jsonify({"reply": f"تم تحديث نقطة الشحن: {updated['chargepoint_name']}"})
            return jsonify({"reply": "تمت الموافقة على العملية."})
        if normalized in {"لا", "الغاء", "إلغاء", "no", "n"}:
            session.pop("pending_owner_action", None)
            return jsonify({"reply": "تم إلغاء العملية، ولم يتم تنفيذ أي تغيير."})
        return jsonify({"reply": "اكتب «نعم» للتأكيد أو «إلغاء» لإيقاف العملية."})

    delete_words = ("احذف", "حذف", "شيل", "إزالة", "ازالة", "remove", "delete")
    add_words = ("اضافة", "إضافة", "أضف", "اضف", "add", "create", "new", "انشاء", "أنشئ")
    update_words = ("تعديل", "عدل", "تحديث", "اجعل", "خلي", "تقبل", "يدعم", "update", "edit", "حدث")

    if any(word in normalized for word in add_words):
        payload_data = {
            "chargepoint_name": _extract_name_from_message(message),
            "area": _extract_area_from_message(message),
            "service_type": _extract_service_from_message(message),
            "status": _extract_status_from_message(message),
            "capacity": max(1, _extract_numeric_value(message, ("السعة", "capacity"))),
            "waiting_count": max(0, _extract_numeric_value(message, ("الانتظار", "waiting", "منتظر"))),
            "opening_hours": "08:00-22:00",
            "description": f"تمت الإضافة عبر المساعد في {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "last_update": datetime.now().isoformat(timespec="seconds"),
        }
        session["pending_owner_action"] = {
            "action": "add",
            "chargepoint_name": payload_data["chargepoint_name"],
            "data": payload_data,
        }
        return jsonify({"reply": _pending_action_reply(session["pending_owner_action"])})

    if any(word in normalized for word in update_words):
        owned_points = db.get_chargepoints(owner_id)
        target_name = re.sub(r"^(?:تعديل|عدل|تحديث|حدث|update|edit)\s*(?:نقطة\s*شحن\s*)?", "", message, flags=re.IGNORECASE).strip()
        candidate = next(
            (point for point in owned_points if _name_match(point["chargepoint_name"], target_name) or target_name in _casefold_text(point["chargepoint_name"])),
            None,
        )
        if candidate is None:
            candidate = next((point for point in owned_points if _casefold_text(point["chargepoint_name"]) in normalized), None)
        if candidate is None:
            return jsonify({"reply": "لم أجد نقطة مملوكة لك بهذا الاسم. اكتب اسم النقطة كما يظهر في القائمة."})

        extracted = extract_update(db, message)
        updates = {}
        if extracted.get("status"):
            updates["status"] = extracted["status"]
        if extracted.get("waiting_count") is not None:
            updates["waiting_count"] = int(extracted["waiting_count"])
        if extracted.get("opening_hours"):
            updates["opening_hours"] = extracted["opening_hours"]
        if extracted.get("note"):
            updates["description"] = extracted["note"]

        requested_area = _extract_area_from_message(message)
        if requested_area != "غير محدد":
            updates["area"] = requested_area

        requested_services = _extract_requested_services(message)
        existing_services = str(candidate.get("service_type", ""))
        services_to_add = [
            service for service in requested_services
            if not service_matches(service, existing_services)
        ]
        if services_to_add:
            updates["service_type"] = "، ".join(
                part.strip()
                for part in (existing_services, *services_to_add)
                if part.strip()
            )
        if updates:
            updates["last_update"] = datetime.now().isoformat(timespec="seconds")

        if requested_services and not services_to_add and not updates:
            return jsonify({
                "reply": f"هذه النقطة تدعم بالفعل: {' و'.join(requested_services)}. لم أغيّر بيانات أخرى."
            })

        if not updates:
            updates = {
                "status": _extract_status_from_message(message),
                "waiting_count": max(0, _extract_numeric_value(message, ("الانتظار", "waiting", "منتظر"))),
                "opening_hours": "08:00-22:00",
                "last_update": datetime.now().isoformat(timespec="seconds"),
            }

        session["pending_owner_action"] = {
            "action": "update",
            "chargepoint_id": candidate["chargepoint_id"],
            "chargepoint_name": candidate["chargepoint_name"],
            "data": updates,
        }
        return jsonify({"reply": _pending_action_reply(session["pending_owner_action"])})

    if not any(word in normalized for word in delete_words):
        return jsonify({"reply": "أستطيع تنفيذ إضافة أو تعديل أو حذف نقطة شحن بعد طلب واضح ثم تأكيدك."})

    owned_points = db.get_chargepoints(owner_id)
    candidates = [
        point for point in owned_points
        if _name_match(point["chargepoint_name"], message)
        or _casefold_text(point["chargepoint_name"]) in normalized
        or normalized in _casefold_text(point["chargepoint_name"])
    ]
    if not candidates:
        return jsonify({"reply": "لم أجد نقطة مملوكة لك بهذا الاسم. اكتب اسم النقطة كما يظهر في القائمة."})

    point = candidates[0]
    session["pending_owner_action"] = {
        "action": "delete",
        "chargepoint_id": point["chargepoint_id"],
        "chargepoint_name": point["chargepoint_name"],
    }
    return jsonify({"reply": _pending_action_reply(session["pending_owner_action"])})


@main.post("/api/owner/extract-update")
def owner_extract_update():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message", "")).strip()
    if not message:
        return jsonify({"error": "أدخل رسالة المالك"}), 400
    return jsonify(extract_update(db, message))
