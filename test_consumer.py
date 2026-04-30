#!/usr/bin/env python3
"""
Unit tests for rabbitmq_to_clickhouse.py
=========================================
Tests the pure-logic functions WITHOUT requiring RabbitMQ or ClickHouse.

Run:  python test_consumer.py
"""

import sys
import os
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

# Ensure the consumer module can be imported even if LOG_DIR doesn't exist
os.makedirs("/tmp/test_logs", exist_ok=True)
with patch.dict(os.environ, {"LOG_DIR": "/tmp/test_logs"}):
    pass

# Patch the LOG_DIR before importing the module (it creates log files at import time)
import importlib

# We need to handle the case where /app/logs doesn't exist (local dev)
# Temporarily patch os.makedirs to avoid issues
_original_makedirs = os.makedirs
os.makedirs = lambda *a, **kw: _original_makedirs(*a, **{**kw, "exist_ok": True})

# Force log dir to /tmp for testing
_log_dir_patch = patch.dict("os.environ", {})
_log_dir_patch.start()

# Monkeypatch the log directory before import
import rabbitmq_to_clickhouse as consumer

os.makedirs = _original_makedirs


class TestIsHeartbeat(unittest.TestCase):
    """Tests for is_heartbeat()."""

    def test_heartbeat_message(self):
        msg = {
            "schema": {"name": "io.debezium.connector.common.Heartbeat"},
            "payload": {"ts_ms": 1772827708760},
        }
        self.assertTrue(consumer.is_heartbeat(msg))

    def test_cdc_message_is_not_heartbeat(self):
        msg = {
            "schema": {"type": "struct", "name": "lis.lis_tarqeem.patients.Envelope"},
            "payload": {
                "before": None,
                "after": {"id": 1, "name": "Test"},
                "op": "c",
                "ts_ms": 1772827721889,
            },
        }
        self.assertFalse(consumer.is_heartbeat(msg))

    def test_no_schema_key(self):
        msg = {"payload": {"op": "c", "after": {"id": 1}}}
        self.assertFalse(consumer.is_heartbeat(msg))

    def test_schema_is_string(self):
        msg = {"schema": "some-string", "payload": {}}
        self.assertFalse(consumer.is_heartbeat(msg))

    def test_empty_message(self):
        self.assertFalse(consumer.is_heartbeat({}))


class TestValidateCdcMessage(unittest.TestCase):
    """Tests for validate_cdc_message()."""

    def test_valid_create(self):
        msg = {"payload": {"op": "c", "after": {"id": 1}}}
        valid, reason = consumer.validate_cdc_message(msg)
        self.assertTrue(valid)
        self.assertEqual(reason, "")

    def test_valid_read(self):
        msg = {"payload": {"op": "r", "after": {"id": 1}}}
        valid, _ = consumer.validate_cdc_message(msg)
        self.assertTrue(valid)

    def test_valid_update(self):
        msg = {"payload": {"op": "u", "before": {"id": 1}, "after": {"id": 1, "name": "new"}}}
        valid, _ = consumer.validate_cdc_message(msg)
        self.assertTrue(valid)

    def test_valid_delete(self):
        msg = {"payload": {"op": "d", "before": {"id": 1}}}
        valid, _ = consumer.validate_cdc_message(msg)
        self.assertTrue(valid)

    def test_missing_payload(self):
        valid, reason = consumer.validate_cdc_message({"schema": {}})
        self.assertFalse(valid)
        self.assertIn("payload", reason)

    def test_missing_op(self):
        msg = {"payload": {"after": {"id": 1}}}
        valid, reason = consumer.validate_cdc_message(msg)
        self.assertFalse(valid)
        self.assertIn("op", reason)

    def test_unsupported_op(self):
        msg = {"payload": {"op": "x"}}
        valid, reason = consumer.validate_cdc_message(msg)
        self.assertFalse(valid)
        self.assertIn("unsupported", reason)

    def test_payload_not_dict(self):
        msg = {"payload": "string-value"}
        valid, reason = consumer.validate_cdc_message(msg)
        self.assertFalse(valid)


class TestParseTimestamp(unittest.TestCase):
    """Tests for parse_timestamp()."""

    def test_epoch_ms(self):
        # 2026-03-06T20:08:41 UTC ≈ 1772827721000 ms
        result = consumer.parse_timestamp(1772827721000)
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2026)

    def test_epoch_ms_zero(self):
        result = consumer.parse_timestamp(0)
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 1970)

    def test_iso_string(self):
        result = consumer.parse_timestamp("2026-03-06T20:08:41Z")
        self.assertIsInstance(result, datetime)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 3)
        self.assertEqual(result.day, 6)

    def test_iso_string_with_offset(self):
        result = consumer.parse_timestamp("2026-03-06T22:08:41+02:00")
        self.assertIsInstance(result, datetime)

    def test_none(self):
        self.assertIsNone(consumer.parse_timestamp(None))

    def test_garbage_string(self):
        self.assertIsNone(consumer.parse_timestamp("not-a-date"))

    def test_empty_string(self):
        self.assertIsNone(consumer.parse_timestamp(""))

    def test_float_epoch(self):
        result = consumer.parse_timestamp(1772827721889.0)
        self.assertIsInstance(result, datetime)


class TestCoerceValue(unittest.TestCase):
    """Tests for coerce_value()."""

    def test_iso_timestamp_string(self):
        result = consumer.coerce_value("2026-03-06T20:08:41Z")
        self.assertIsInstance(result, datetime)

    def test_regular_string_not_converted(self):
        result = consumer.coerce_value("John Doe")
        self.assertEqual(result, "John Doe")

    def test_integer_passthrough(self):
        self.assertEqual(consumer.coerce_value(42), 42)

    def test_none_passthrough(self):
        self.assertIsNone(consumer.coerce_value(None))

    def test_short_string_not_parsed(self):
        result = consumer.coerce_value("2026-03")
        self.assertEqual(result, "2026-03")


class TestProcessCdcEvent(unittest.TestCase):
    """Tests for process_cdc_event() with a mocked ClickHouse client."""

    def setUp(self):
        self.mock_ch = MagicMock()
        # Simulate table already exists
        self.mock_ch.query.return_value = MagicMock(result_rows=[[1]])
        # Reset stats
        consumer.stats = {"processed": 0, "errors": 0, "skipped": 0, "heartbeats": 0, "last_processed": None}

    def test_create_event(self):
        msg = {
            "payload": {
                "op": "c",
                "after": {"id": 1, "name": "Test Patient"},
                "source": {"table": "patients"},
                "ts_ms": 1772827721889,
            }
        }
        result = consumer.process_cdc_event(self.mock_ch, msg)
        self.assertTrue(result)
        self.mock_ch.insert.assert_called_once()
        self.assertEqual(consumer.stats["processed"], 1)

    def test_snapshot_event(self):
        msg = {
            "payload": {
                "op": "r",
                "after": {"id": 2, "name": "Snapshot Row"},
                "source": {"table": "patients"},
                "ts_ms": 1772827721889,
            }
        }
        result = consumer.process_cdc_event(self.mock_ch, msg)
        self.assertTrue(result)
        self.mock_ch.insert.assert_called_once()

    def test_update_event(self):
        msg = {
            "payload": {
                "op": "u",
                "before": {"id": 3, "name": "Old Name"},
                "after": {"id": 3, "name": "New Name"},
                "source": {"table": "patients"},
                "ts_ms": 1772827721889,
            }
        }
        result = consumer.process_cdc_event(self.mock_ch, msg)
        self.assertTrue(result)
        # Should have attempted delete + insert
        self.mock_ch.command.assert_called()
        self.mock_ch.insert.assert_called_once()

    def test_delete_event(self):
        msg = {
            "payload": {
                "op": "d",
                "before": {"id": 4, "name": "To Delete"},
                "source": {"table": "patients"},
                "ts_ms": 1772827721889,
            }
        }
        result = consumer.process_cdc_event(self.mock_ch, msg)
        self.assertTrue(result)
        self.mock_ch.command.assert_called()
        # Should NOT insert for deletions
        self.mock_ch.insert.assert_not_called()

    def test_create_with_iso_timestamp(self):
        msg = {
            "payload": {
                "op": "c",
                "after": {"id": 5, "created_at": "2026-03-06T20:08:41Z"},
                "source": {"table": "patients"},
                "ts_ms": 1772827721889,
            }
        }
        result = consumer.process_cdc_event(self.mock_ch, msg)
        self.assertTrue(result)
        # Verify the inserted values contain a datetime for created_at
        call_args = self.mock_ch.insert.call_args
        row_values = call_args[0][1][0]  # First row
        column_names = call_args[1]["column_names"]
        idx = column_names.index("created_at")
        self.assertIsInstance(row_values[idx], datetime)

    def test_empty_after_payload(self):
        msg = {
            "payload": {
                "op": "c",
                "after": {},
                "source": {"table": "patients"},
                "ts_ms": 1772827721889,
            }
        }
        result = consumer.process_cdc_event(self.mock_ch, msg)
        # Empty record = nothing to insert, should still succeed (ACK)
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
