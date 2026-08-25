"""
Purpose: Verifies structured terminal events remain machine-readable and only
contain explicitly selected privacy-safe optimization fields.
"""

import json
import logging

from app.logging_config import JsonTerminalFormatter


# Confirms optimization logs are one-line JSON with safe, searchable metrics.
def test_structured_terminal_log_is_json_and_contains_metrics():
    record = logging.LogRecord("vendor_trust.test", logging.INFO, __file__, 1,
                               "assessment_completed", (), None)
    record.event_fields = {"duration_ms": 125.4, "risk_score": 7.5, "field_count": 24}
    parsed = json.loads(JsonTerminalFormatter().format(record))
    assert parsed["event"] == "assessment_completed"
    assert parsed["duration_ms"] == 125.4 and parsed["field_count"] == 24
    assert "timestamp" in parsed and "email" not in parsed and "description" not in parsed
