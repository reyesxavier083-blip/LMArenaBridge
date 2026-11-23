# LEYRA — OpenAI Ads Conversions (validate-only)

The standard-library gateway exposes two authenticated routes:

- `POST /leyra/integrations/ads/conversions/preview`: validates the event batch locally. It never contacts OpenAI.
- `POST /leyra/integrations/ads/conversions/validate`: sends the batch to OpenAI Ads with `validate_only=true`. It cannot persist conversion events.

Both routes require `Authorization: Bearer $LEYRA_GATEWAY_TOKEN` and a JSON body containing only an `events` array. The gateway rejects unknown event fields, duplicate IDs, unsupported event types, invalid timestamps, malformed web URLs, and invalid event data. Batches are limited to 1,000 events and request bodies to 2 MiB.

## Server configuration

Set these variables in the private deployment environment, never in a browser, mobile app, source file, or Git repository:

- `OPENAI_CONVERSIONS_API_KEY`: OpenAI Ads Conversions API credential.
- `OPENAI_ADS_PIXEL_ID`: conversion source / Pixel ID.
- `LEYRA_OPENAI_ADS_ENABLED=true`: explicit opt-in required for remote validation.

The existing `LEYRA_GATEWAY_TOKEN` remains the client-to-gateway credential. It is not the OpenAI Ads credential. `LEYRA_UPSTREAM_API_KEY` is unrelated and is not used for Ads Conversions.

Remote validation fails closed when the feature flag or either Ads credential is missing. Provider response bodies are size-limited; provider error bodies and credentials are not returned to clients or logged.

## Privacy safeguards

This integration intentionally rejects the `user` identifier object. Do not add personal identifiers, hashed identifiers, advertising IDs, IP addresses, or user-agent data to conversion events. Only submit events when the relevant user has provided valid consent and the organization has confirmed an appropriate legal basis. Events marked `opt_out=true` are rejected. Apply data minimization and retention limits in the system that creates the events.

## Example request

```json
{
  "events": [
    {
      "id": "evt-unique-001",
      "type": "registration_completed",
      "timestamp_ms": 1795392000000,
      "action_source": "web",
      "source_url": "https://example.com/signup/complete",
      "data": {"type": "customer_action"}
    }
  ]
}
```

Use the preview route first. Only after reviewing the batch and confirming consent and private server configuration should an operator call the remote validation route. A successful validation is not the same as a persisted conversion. This change deliberately provides no persistence route; adding one requires a separate review and explicit authorization.

## Current scope

This PR adds a validate-only adapter to the standard-library gateway used by the Render service start command. It does not configure secrets, enable the feature flag, deploy the service, connect an Ads Manager account, or transmit production conversions.
