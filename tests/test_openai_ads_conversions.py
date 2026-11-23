"""Focused tests for the privacy-minimized OpenAI Ads adapter."""
import json
import os
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.openai_ads_conversions import (
    AdsProviderError,
    AdsValidationError,
    validate_events,
    validate_remotely,
)


def valid_event():
    return {
        "id": "evt-unique-001",
        "type": "registration_completed",
        "timestamp_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
        "action_source": "web",
        "source_url": "https://example.com/signup/complete",
        "data": {"type": "customer_action"},
    }


class OpenAIAdsConversionsTests(unittest.TestCase):
    def test_valid_event_batch(self):
        self.assertEqual(len(validate_events([valid_event()])), 1)

    def test_duplicate_ids_are_rejected(self):
        event = valid_event()
        with self.assertRaises(AdsValidationError):
            validate_events([event, dict(event)])

    def test_user_identifiers_are_rejected(self):
        event = valid_event()
        event["user"] = {"emails_sha256": ["a" * 64]}
        with self.assertRaises(AdsValidationError):
            validate_events([event])

    def test_opted_out_event_is_rejected(self):
        event = valid_event()
        event["opt_out"] = True
        with self.assertRaises(AdsValidationError):
            validate_events([event])

    @patch.dict(os.environ, {
        "LEYRA_OPENAI_ADS_ENABLED": "false",
        "OPENAI_CONVERSIONS_API_KEY": "test-secret",
        "OPENAI_ADS_PIXEL_ID": "test-pixel",
    }, clear=False)
    def test_remote_validation_is_disabled_by_default(self):
        with self.assertRaises(AdsProviderError):
            validate_remotely([valid_event()])

    @patch.dict(os.environ, {
        "LEYRA_OPENAI_ADS_ENABLED": "true",
        "OPENAI_CONVERSIONS_API_KEY": "test-secret",
        "OPENAI_ADS_PIXEL_ID": "test-pixel",
    }, clear=False)
    @patch("src.openai_ads_conversions.urlopen")
    def test_remote_request_is_always_validate_only(self, mocked_urlopen):
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"valid":true}'
        response.__enter__.return_value = response
        response.__exit__.return_value = False
        mocked_urlopen.return_value = response

        result = validate_remotely([valid_event()])
        request = mocked_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))

        self.assertTrue(payload["validate_only"])
        self.assertEqual(payload["events"][0]["id"], "evt-unique-001")
        self.assertEqual(result["status_code"], 200)
        self.assertIn("pid=test-pixel", request.full_url)


if __name__ == "__main__":
    unittest.main()
