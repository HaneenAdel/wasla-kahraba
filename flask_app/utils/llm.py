"""Three course agents for Wasla Kahraba.
Uses the OpenAI-compatible proxy when OPENAI_API_KEY is configured and keeps a
safe local fallback for classroom/demo runs without an API key.
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any
from difflib import SequenceMatcher

MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")

def _normalize_search_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()

    value = "".join(
        character
        for character in value
        if unicodedata.category(character) != "Mn"
    )

    value = value.replace("–", "-").replace("—", "-")

    return re.sub(r"\s+", " ", value).strip()

def _point_name_matches_query(point_name: str, query: str) -> bool:
    """Match a full point name or a meaningful shortened name in the query."""

    normalized_name = _normalize_search_text(point_name)
    normalized_query = _normalize_search_text(query)

    if normalized_name in normalized_query:
        return True

    ignored_words = {
        "هل",
        "يوجد",
        "نقطة",
        "الشحن",
        "شحن",
        "متاحة",
        "متاح",
        "مفتوحة",
        "مفتوح",
        "مغلقة",
        "مغلق",
        "الفرع",
        "فرع",
    }

    name_words = [
        word
        for word in re.findall(
            r"[\w\u0600-\u06ff]+",
            normalized_name,
        )
        if word not in ignored_words and len(word) > 2
    ]

    query_words = {
        word
        for word in re.findall(
            r"[\w\u0600-\u06ff]+",
            normalized_query,
        )
        if word not in ignored_words and len(word) > 2
    }
    matched_words = sum(
        1
        for word in name_words
        if word in query_words
    )

    return matched_words >= 2


def normalize_arabic(text: str) -> str:
    text = str(text or "").strip().lower()

    text = "".join(
        char
        for char in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(char)
    )

    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ة": "ه",
        "ؤ": "و",
        "ئ": "ي",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    text = re.sub(r"\bال", "", text)
    text = re.sub(r"[^\w\s\u0600-\u06ff]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    return text


def arabic_tokens(text: str) -> list[str]:
    return normalize_arabic(text).split()


def area_match_score(user_text: str, area: str) -> int:
    query = normalize_arabic(user_text)
    normalized_area = normalize_arabic(area)

    if not query or not normalized_area:
        return 0

    query_tokens = arabic_tokens(query)
    area_tokens = arabic_tokens(normalized_area)

    score = 0

    if normalized_area in query:
        score += 100

    if query in normalized_area:
        score += 80

    for query_token in query_tokens:
        for area_token in area_tokens:
            if len(query_token) >= 2 and area_token.startswith(query_token):
                score += 30
            elif len(area_token) >= 2 and query_token.startswith(area_token):
                score += 20
            elif SequenceMatcher(
                None,
                query_token,
                area_token,
            ).ratio() >= 0.70:
                score += 10

    return score


def extract_area_from_database(db, text: str) -> str | None:
    rows = db.query(
        """
        SELECT DISTINCT area
        FROM chargepoint
        WHERE area IS NOT NULL
        AND TRIM(area) != ''
        """
    )

    areas = [row["area"] for row in rows if row.get("area")]

    if not areas:
        return None

    ranked_areas = sorted(
        areas,
        key=lambda area: area_match_score(text, area),
        reverse=True,
    )

    best_area = ranked_areas[0]
    score = area_match_score(text, best_area)

    return best_area if score >= 20 else None


def load_roles(db):
    return db.get_llm_roles()


def _client():
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        from openai import OpenAI
        return OpenAI()
    except Exception:
        return None


def _role_prompt(roles: dict[str, dict[str, Any]], name: str, fallback: str) -> str:
    role = roles.get(name, {})
    return role.get("specific_instructions") or fallback


def synthesize_response(db, request_text: str, points: list[dict[str, Any]]) -> str:
    roles = load_roles(db)
    fallback = 'Write a short warm Arabic response based only on the supplied results. Mention last update and uncertainty.'
    client = _client()
    if client:
        try:
            response = client.chat.completions.create(model=MODEL, messages=[{"role": "system", "content": _role_prompt(roles, "Response Synthesis Expert", fallback)}, {"role": "user", "content": json.dumps({"request": request_text, "points": points}, ensure_ascii=False)}], max_completion_tokens=350)
            return response.choices[0].message.content.strip()
        except Exception:
            pass
    if not points:
        return "لم نجد نقطة شحن مطابقة لطلبك وفق آخر البيانات المتاحة."
    names = " و".join(point["chargepoint_name"] for point in points[:2])
    return f"قد تكون {names} مناسبة لطلبك وفق آخر تحديث. التوفر قد يتغير، لذلك يُفضّل التحقق قبل التوجه."


def extract_update(db, message: str) -> dict[str, Any]:
    roles = load_roles(db)
    fallback = 'Extract only explicitly stated status, waiting_count, opening_hours, and note as JSON.'
    client = _client()
    if client:
        try:
            response = client.chat.completions.create(model=MODEL, messages=[{"role": "system", "content": _role_prompt(roles, "Update Extraction Expert", fallback)}, {"role": "user", "content": message}], response_format={"type": "json_object"}, max_completion_tokens=300)
            return json.loads(response.choices[0].message.content)
        except Exception:
            pass
    status = None
    if any(word in message for word in ["مليان", "ممتلئ", "ما في مكان"]): status = "full"
    elif any(word in message for word in ["مسكر", "مغلق", "مقفول"]): status = "closed"
    elif any(word in message for word in ["عطل", "متوقف"]): status = "temporarily_off"
    elif any(word in message for word in ["شغال", "فاتح", "متاح"]): status = "open"
    match = re.search(r"(?:المنتظرين|انتظار|منتظر)\D*(\d+)", message)
    hours = re.search(r"(\d{1,2}:\d{2}\s*[-–إلى]\s*\d{1,2}:\d{2})", message)
    return {"status": status, "waiting_count": int(match.group(1)) if match else None, "opening_hours": hours.group(1) if hours else None, "note": None}


def service_matches(
    requested_service: str,
    point_service: str,
) -> bool:
    requested = normalize_arabic(requested_service)
    available = normalize_arabic(point_service)

    if not requested or not available:
        return False

    if requested in {
        "شحن لابتوب",
        "شحن كمبيوتر",
        "شحن حاسوب",
        "شحن حاسب",
    }:
        return any(
            word in available
            for word in [
                "لابتوب",
                "لاب توب",
                "كمبيوتر",
                "حاسوب",
                "حاسب",
                "جهاز كبير",
                "جهاز متوسط",
                
            ]
        )

    if requested == "شحن هاتف":
        return (
            any(
                word in available
                for word in [
                    "هاتف",
                    "تلفون",
                    "موبايل",
                    "جوال",
                    "هاتف محمول",
                ]
            )
            or "جهاز صغير" in available
        )

    if requested in {
        "شحن جهاز صغير",
        "شحن جهاز طبي صغير",
    }:
        return "جهاز صغير" in available

    return requested in available


def point_name_match_score(user_text: str, point_name: str) -> int:
    query = normalize_arabic(user_text)
    name = normalize_arabic(point_name)

    if not query or not name:
        return 0

    if name in query:
        return 100

    # مطابقة اسم مختصر مثل:
    # مركز المجتمع - الفرع الرئيسي
    short_name = name.replace("نقطه ", "").strip()

    if short_name in query:
        return 90

    query_tokens = set(arabic_tokens(query))
    name_tokens = set(arabic_tokens(short_name))

    important_tokens = {
        token
        for token in name_tokens
        if len(token) >= 3
        and token not in {"الفرع", "نقطه"}
    }

    matched = sum(
        1
        for token in important_tokens
        if any(
            token.startswith(query_token)
            or query_token.startswith(token)
            for query_token in query_tokens
            if len(query_token) >= 2
        )
    )

    if important_tokens and matched == len(important_tokens):
        return 80

    if matched >= 2:
        return 50

    return 0


def find_requested_point(db, text: str) -> dict[str, Any] | None:
    points = db.get_chargepoints()

    ranked = sorted(
        points,
        key=lambda point: point_name_match_score(
            text,
            point.get("chargepoint_name", ""),
        ),
        reverse=True,
    )

    if not ranked:
        return None

    best = ranked[0]
    score = point_name_match_score(
        text,
        best.get("chargepoint_name", ""),
    )

    return best if score >= 50 else None


def find_requested_points(db, text: str) -> list[dict[str, Any]]:
    query = normalize_arabic(text)

    generic_words = {
        "نقطه",
        "نقاط",
        "مركز",
        "الفرع",
        "فرع",
        "المتاحه",
        "متاحه",
        "متاح",
        "مفتوحه",
        "مفتوح",
        "هل",
        "في",
        "وين",
        "شحن",
    }

    query_tokens = {
        token
        for token in arabic_tokens(query)
        if len(token) >= 3
        and token not in generic_words
    }

    if not query_tokens:
        return []

    matches = []

    for point in db.get_chargepoints():
        point_name = normalize_arabic(
            point.get("chargepoint_name", "")
        )

        point_tokens = set(arabic_tokens(point_name))

        matched = any(
            query_token in point_name
            or any(
                point_token.startswith(query_token)
                for point_token in point_tokens
            )
            for query_token in query_tokens
        )

        if matched:
            matches.append(point)

    return matches

def _normalize_search_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).lower()

    value = "".join(
        character
        for character in value
        if unicodedata.category(character) != "Mn"
    )

    value = value.replace("–", "-").replace("—", "-")

    return re.sub(r"\s+", " ", value).strip()


def detect_explicit_area(text: str) -> str | None:
    normalized = normalize_arabic(text)

    area_aliases = {
        "المنطقة الشمالية": [
            "المنطقه الشماليه",
            "المنطقه الشمال",
            "بالمنطقة الشمالية",
            "الشماليه",
            "الشمال",
            "شمال",
        ],
        "المنطقة الوسطى": [
            "المنطقه الوسطي",
            "المنطقه الوسطى",
            "بالمنطقة الوسطى",
            "الوسطي",
            "الوسطى",
            "الوسط",
            "وسط",
        ],
        "المنطقة الغربية": [
            "المنطقه الغربيه",
            "بالمنطقة الغربية",
            "الغربيه",
            "الغربية",
            "الغرب",
            "غرب",
        ],
        "المنطقة الشرقية": [
            "المنطقه الشرقيه",
            "بالمنطقة الشرقية",
            "الشرقيه",
            "الشرقية",
            "الشرق",
            "شرق",
        ],
    }

    for canonical_area, aliases in area_aliases.items():
        for alias in aliases:
            if normalize_arabic(alias) in normalized:
                return canonical_area

    return None

def understand_request(db, text: str) -> dict[str, Any]:
    roles = load_roles(db)

    fallback = (
        "Extract service, area, and waiting preference as JSON. "
        "Default service to شحن هاتف."
    )

    lowered = text.lower()

    laptop_terms = (
        "لابتوب",
        "لاب توب",
        "حاسوب محمول",
        "كمبيوتر محمول",
        "laptop",
        "notebook",
    )

    requested_laptop = any(term in lowered for term in laptop_terms)

    client = _client()

    if client:
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": _role_prompt(
                            roles,
                            "Request Understanding Expert",
                            fallback,
                        ),
                    },
                    {
                        "role": "user",
                        "content": text,
                    },
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "request",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "properties": {
                                "service": {
                                    "type": "string",
                                },
                                "area": {
                                    "type": ["string", "null"],
                                },
                                "waiting_preference": {
                                    "type": "string",
                                    "enum": ["low", "any"],
                                },
                            },
                            "required": [
                                "service",
                                "area",
                                "waiting_preference",
                            ],
                            "additionalProperties": False,
                        },
                    },
                },
                max_completion_tokens=300,
            )

            result = json.loads(
                response.choices[0].message.content
            )

            if requested_laptop:
                result["service"] = "شحن لابتوب"

            return result

        except Exception:
            pass

    areas = [
        "المنطقة الوسطى",
        "المنطقة الغربية",
        "المنطقة الشرقية",
        "المنطقة الشمالية",
        "الوسطى",
        "الغربية",
        "الشرقية",
        "الشمالية",
        "الرمال",
    ]

    area = next(
        (item for item in areas if item in text),
        None,
    )

    preference = (
        "low"
        if any(
            word in lowered
            for word in [
                "قليل",
                "كثير",
                "انتظار",
                "أستنى",
                "استنى",
            ]
        )
        else "any"
    )

    if requested_laptop:
        service = "شحن لابتوب"
    elif "طبي" in text:
        service = "شحن جهاز طبي صغير"
    else:
        service = "شحن هاتف"

    return {
        "service": service,
        "area": area,
        "waiting_preference": preference,
    }

