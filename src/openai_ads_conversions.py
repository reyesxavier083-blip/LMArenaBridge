"""Server-side, validate-only OpenAI Ads Conversions API integration.

No event persistence is exposed by this module. Remote requests always send
validate_only=true. Credentials are read only from the server environment.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://bzr.openai.com/v1/events"
MAX_EVENTS = 1000
EVENT_DATA_TYPES = {
    "app_installed": "customer_action",
    "app_opened": "customer_action",
    "appointment_scheduled": "customer_action",
    "checkout_started": "contents",
    "contents_viewed": "contents",
    "custom": "custom",
    "items_added": "contents",
    "lead_created": "customer_action",
    "order_created": "contents",
    "page_viewed": "contents",
    "registration_completed": "customer_action",
    "subscription_created": "plan_enrollment",
    "trial_started": "plan_enrollment",
}
EVENT_FIELDS = {
    "id", "type", "timestamp_ms", "custom_event_name", "oppref",
    "source_url", "action_source", "user", "opt_out", "data",
}
HASHED_USER_FIELDS = {
    "phone_numbers_sha256", "emails_sha256", "external_ids_sha256",
    "first_names_sha256", "last_names_sha256",
}
USER_FIELDS = HASHED_USER_FIELDS | {
    "obref", "countries", "cities", "regions", "postal_codes",
    "android_advertising_id", "ip_address", "user_agent",
}
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
CUSTOM_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,62}[A-Za-z0-9]$|^[A-Za-z0-9]$")


class AdsValidationError(ValueError):
    pass


class AdsProviderError(RuntimeError):
    pass


def validate_events(events: object) -> list[dict]:
    if not isinstance(events, list) or not events or len(events) > MAX_EVENTS:
        raise AdsValidationError("events must be a non-empty list of at most 1000 items")
    now = datetime.now(timezone.utc)
    result = []
    ids = set()
    for event in events:
        if not isinstance(event, dict) or set(event) - EVENT_FIELDS:
            raise AdsValidationError("event must be an object containing only supported fields")
        event_id, event_type = event.get("id"), event.get("type")
        if not isinstance(event_id, str) or not event_id.strip() or event_id in ids:
            raise AdsValidationError("event id must be non-empty and unique within the batch")
        ids.add(event_id)
        if event_type not in EVENT_DATA_TYPES:
            raise AdsValidationError("unsupported conversion event type")
        timestamp = event.get("timestamp_ms")
        if isinstance(timestamp, bool) or not isinstance(timestamp, int):
            raise AdsValidationError("timestamp_ms must be an integer Unix timestamp in milliseconds")
        try:
            event_time = datetime.fromtimestamp(timestamp / 1000, tz=timezone.utc)
        except (OverflowError, OSError, ValueError) as exc:
            raise AdsValidationError("timestamp_ms is outside the supported range") from exc
        if event_time < now - timedelta(days=7) or event_time > now + timedelta(minutes=10):
            raise AdsValidationError("timestamp_ms must be within the last 7 days and at most 10 minutes ahead")
        source = event.get("action_source")
        if source not in {"web", "mobile_app", "offline", "physical_store", "phone_call", "email", "other"}:
            raise AdsValidationError("action_source is required and unsupported")
        if event_type in {"app_installed", "app_opened"} and source != "mobile_app":
            raise AdsValidationError("app lifecycle events require mobile_app action_source")
        if source == "web":
            from urllib.parse import urlsplit
            parsed = urlsplit(event.get("source_url", ""))
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password:
                raise AdsValidationError("web events require a valid source_url")
        data = event.get("data")
        expected = EVENT_DATA_TYPES[event_type]
        if not isinstance(data, dict) or data.get("type") != expected:
            raise AdsValidationError("event data.type does not match the selected event type")
        if "amount" in data:
            amount = data["amount"]
            if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
                raise AdsValidationError("data.amount must be a non-negative integer")
            currency = data.get("currency")
            if not isinstance(currency, str) or not re.fullmatch(r"[A-Za-z]{3}", currency):
                raise AdsValidationError("data.currency must be a three-letter currency code")
        if event_type == "custom":
            name = event.get("custom_event_name")
            if not isinstance(name, str) or not CUSTOM_NAME_RE.fullmatch(name):
                raise AdsValidationError("custom events require a valid custom_event_name")
        elif "custom_event_name" in event:
            raise AdsValidationError("custom_event_name is only valid for custom events")
        if "opt_out" in event and not isinstance(event["opt_out"], bool):
            raise AdsValidationError("opt_out must be a boolean")
        if "user" in event:
            user = event["user"]
            if not isinstance(user, dict) or set(user) - USER_FIELDS:
                raise AdsValidationError("user contains unsupported identifier fields")
            for field in HASHED_USER_FIELDS.intersection(user):
                values = user[field]
                if not isinstance(values, list) or len(values) > 3 or any(
                    not isinstance(value, str) or not HASH_RE.fullmatch(value) for value in values
                ):
                    raise AdsValidationError("user hashed identifiers must be lowercase SHA-256 digests")
        result.append(dict(event))
    return result


def _configuration() -> tuple[str, str]:
    if os.getenv("LEYRA_OPENAI_ADS_ENABLED", "false").strip().lower() not in {"1", "true", "yes", "on"}:
        raise AdsProviderError("OpenAI Ads integration is disabled")
    key = os.getenv("OPENAI_CONVERSIONS_API_KEY", "").strip()
    pixel_id = os.getenv("OPENAI_ADS_PIXEL_ID", "").strip()
    if not key or not pixel_id:
        raise AdsProviderError("OpenAI Ads server credentials are not configured")
    return key, pixel_id


def validate_remotely(events: list[dict], timeout: float = 15.0) -> dict:
    key, pixel_id = _configuration()
    url = ENDPOINT + "?" + urlencode({"pid": pixel_id})
    body = json.dumps({"validate_only": True, "events": events}, separators=(",", ":")).encode("utf-8")
    request = Request(url, data=body, headers={
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }, method="POST")
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(1024 * 1024 + 1)
            if len(raw) > 1024 * 1024:
                raise AdsProviderError("OpenAI Ads validation response exceeded the size limit")
            try:
                parsed = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = {"message": "Provider returned a non-JSON response"}
            return {
                "provider_contacted": True,
                "validate_only": True,
                "event_count": len(events),
                "status_code": response.status,
                "response": parsed if isinstance(parsed, dict) else {"data": parsed},
            }
    except HTTPError as exc:
        # Do not relay provider bodies: they may contain sensitive account details.
        raise AdsProviderError("OpenAI Ads validation rejected the request (HTTP %s)" % exc.code) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise AdsProviderError("Could not reach the OpenAI Ads validation endpoint") from exc
