#!/usr/bin/env python3
"""
RabbitMQ to ClickHouse CDC Consumer
====================================
Consumes Debezium CDC events from RabbitMQ and mirrors them into ClickHouse.

Supported Debezium operations:
  c  → INSERT (new row created)
  r  → SNAPSHOT (initial snapshot read)
  u  → UPDATE  (delete-then-insert mirroring)
  d  → DELETE  (physical delete from ClickHouse)

Handles:
  - Debezium heartbeat messages (silently ACK'd)
  - ISO 8601 and epoch-ms timestamp parsing
  - Robust payload validation
  - Graceful shutdown on SIGINT / SIGTERM
"""

import pika
import json
import time
import signal
import sys
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime

import clickhouse_connect

# ---------------------------------------------------------------------------
# Try importing python-dateutil for robust ISO timestamp parsing.
# Falls back to datetime.fromisoformat if unavailable.
# ---------------------------------------------------------------------------
try:
    from dateutil import parser as dateutil_parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False

# ===========================================================================
#  Configuration
# ===========================================================================
RABBITMQ_HOST = os.environ.get("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_USER = os.environ.get("RABBITMQ_USER", "guest")
RABBITMQ_PASSWORD = os.environ.get("RABBITMQ_PASSWORD", "guest")
QUEUE_NAME = os.environ.get("QUEUE_NAME", "analytics_queue")

CLICKHOUSE_HOST = os.environ.get("CLICKHOUSE_HOST", "clickhouse")
CLICKHOUSE_PORT = int(os.environ.get("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_USER = os.environ.get("CLICKHOUSE_USER", "default")
CLICKHOUSE_PASSWORD = os.environ.get("CLICKHOUSE_PASSWORD", "default")
CH_DATABASE = os.environ.get("CLICKHOUSE_DATABASE", "default")

# Debezium heartbeat schema identifier
HEARTBEAT_SCHEMA_NAME = "io.debezium.connector.common.Heartbeat"

# Valid Debezium CDC operations
VALID_OPS = {"c", "r", "u", "d"}

# ===========================================================================
#  Global state
# ===========================================================================
client = None
running = True
stats = {"processed": 0, "errors": 0, "skipped": 0, "heartbeats": 0, "last_processed": None}

# ===========================================================================
#  Logging
# ===========================================================================
LOG_DIR = "/app/logs"
os.makedirs(LOG_DIR, exist_ok=True)

log_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
log_file = os.path.join(LOG_DIR, "consumer.log")

# Rotating log file: 10 MB per file, keep 5 backups
file_handler = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5)
file_handler.setFormatter(log_formatter)
file_handler.setLevel(logging.DEBUG)

console_handler = logging.StreamHandler()
console_handler.setFormatter(log_formatter)
console_handler.setLevel(logging.INFO)

logger = logging.getLogger("consumer")
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)
logger.addHandler(console_handler)


# ===========================================================================
#  Signal handling
# ===========================================================================
def signal_handler(sig, frame):
    """Handle graceful shutdown."""
    global running
    logger.info("Received shutdown signal. Stopping consumer...")
    running = False


# ===========================================================================
#  Heartbeat detection
# ===========================================================================
def is_heartbeat(message: dict) -> bool:
    """Return True if the message is a Debezium heartbeat."""
    schema = message.get("schema")
    if isinstance(schema, dict):
        return schema.get("name") == HEARTBEAT_SCHEMA_NAME
    return False


# ===========================================================================
#  Message validation
# ===========================================================================
def validate_cdc_message(message: dict) -> tuple:
    """
    Validate that a Debezium CDC message has the required structure.

    Returns:
        (is_valid: bool, reason: str)
    """
    if "payload" not in message:
        return False, "missing 'payload' key"

    payload = message["payload"]
    if not isinstance(payload, dict):
        return False, "'payload' is not a dict"

    if "op" not in payload:
        return False, "missing 'payload.op'"

    op = payload["op"]
    if op not in VALID_OPS:
        return False, f"unsupported operation '{op}'"

    return True, ""


# ===========================================================================
#  Timestamp parsing
# ===========================================================================
def parse_timestamp(value) -> datetime:
    """
    Parse a Debezium timestamp into a Python datetime.

    Handles:
      - int / float  → epoch milliseconds
      - str          → ISO 8601 (e.g. '2026-03-06T20:08:41Z')
      - None / other → returns None
    """
    if value is None:
        return None

    # Epoch milliseconds (Debezium ts_ms)
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(value / 1000.0)
        except (OSError, ValueError, OverflowError):
            return None

    # ISO 8601 string
    if isinstance(value, str):
        try:
            if HAS_DATEUTIL:
                return dateutil_parser.isoparse(value)
            else:
                # Remove trailing 'Z' for datetime.fromisoformat (Python < 3.11)
                cleaned = value.replace("Z", "+00:00")
                return datetime.fromisoformat(cleaned)
        except (ValueError, TypeError):
            return None

    return None


def coerce_value(value):
    """
    Coerce a single field value so ClickHouse can ingest it.

    - ISO timestamp strings → datetime
    - Everything else → pass through
    """
    if isinstance(value, str):
        # Only attempt parsing if it looks like an ISO timestamp
        # Quick heuristic: contains 'T' and has digits on both sides
        if "T" in value and len(value) >= 19:
            parsed = parse_timestamp(value)
            if parsed is not None:
                return parsed
    return value


# ===========================================================================
#  Column type cache & value casting
# ===========================================================================
_column_type_cache = {}  # table_name -> {col_name: ch_type_string}


def _get_column_types(ch_client, table_name: str) -> dict:
    """Get and cache ClickHouse column types for a table."""
    if table_name not in _column_type_cache:
        try:
            result = ch_client.query(
                f"SELECT name, type FROM system.columns WHERE table = %(table)s AND database = %(db)s",
                parameters={"table": table_name, "db": CH_DATABASE},
            )
            _column_type_cache[table_name] = {row[0]: row[1] for row in result.result_rows}
        except Exception:
            _column_type_cache[table_name] = {}
    return _column_type_cache[table_name]


def _cast_value_for_column(value, ch_type: str):
    """
    Cast a Python value to match the ClickHouse column type.

    This prevents 'TypeError: object of type int has no len()' when
    clickhouse_connect expects a str but gets an int (or vice versa).
    """
    if value is None:
        return value

    # Unwrap Nullable(...)
    inner_type = ch_type
    if inner_type.startswith("Nullable("):
        inner_type = inner_type[9:-1]

    # String columns: ensure value is str
    if inner_type in ("String", "LowCardinality(String)"):
        if not isinstance(value, str):
            return str(value)

    # Integer columns: ensure value is int
    elif inner_type in ("Int8", "Int16", "Int32", "Int64",
                        "UInt8", "UInt16", "UInt32", "UInt64"):
        if isinstance(value, str):
            try:
                return int(value)
            except (ValueError, TypeError):
                return 0
        elif isinstance(value, float):
            return int(value)

    # Float columns: ensure value is float
    elif inner_type in ("Float32", "Float64"):
        if isinstance(value, str):
            try:
                return float(value)
            except (ValueError, TypeError):
                return 0.0
        elif isinstance(value, int):
            return float(value)

    # DateTime columns: keep as-is (already handled by coerce_value)
    return value


def _cast_row_for_table(ch_client, table_name: str, columns: list, values: list) -> list:
    """Cast all values in a row to match ClickHouse column types."""
    col_types = _get_column_types(ch_client, table_name)
    if not col_types:
        # Fallback: convert non-string/non-datetime to str for safety
        return [str(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and not isinstance(v, datetime)
                else v for v in values]

    casted = []
    for col_name, val in zip(columns, values):
        ch_type = col_types.get(col_name)
        if ch_type:
            casted.append(_cast_value_for_column(val, ch_type))
        else:
            # Column not in table yet — pass through
            casted.append(val)
    return casted


# ===========================================================================
#  ClickHouse client
# ===========================================================================
def get_clickhouse_client():
    """Get or create a ClickHouse client (singleton)."""
    global client
    if client is None:
        logger.info(f"Connecting to ClickHouse at {CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}...")
        client = clickhouse_connect.get_client(
            host=CLICKHOUSE_HOST,
            port=CLICKHOUSE_PORT,
            username=CLICKHOUSE_USER,
            password=CLICKHOUSE_PASSWORD,
        )
        logger.info("Connected to ClickHouse successfully.")
    return client


# ===========================================================================
#  Dynamic table creation
# ===========================================================================
def create_table_if_not_exists(ch_client, table_name: str, sample_record: dict) -> bool:
    """Dynamically create a ClickHouse table based on the record structure."""
    try:
        result = ch_client.query(f"EXISTS TABLE {table_name}")
        if result.result_rows[0][0] == 1:
            return True

        logger.info(f"Creating table '{table_name}'...")

        # Primary key: 'id' if present, else first column
        pk_col = "id" if "id" in sample_record else list(sample_record.keys())[0]

        columns = []
        for key, value in sample_record.items():
            if isinstance(value, bool):
                col_type = "UInt8"
            elif isinstance(value, int):
                col_type = "Int64"
            elif isinstance(value, float):
                col_type = "Float64"
            elif isinstance(value, datetime):
                col_type = "DateTime"
            else:
                col_type = "String"

            columns.append(f"`{key}` Nullable({col_type})")

        columns_str = ",\n    ".join(columns)

        create_sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            {columns_str},
            `_cdc_operation` String,
            `_cdc_timestamp` DateTime64(3),
            `_ingested_at` DateTime64(3) DEFAULT now64(3)
        )
        ENGINE = MergeTree()
        ORDER BY `{pk_col}`
        SETTINGS allow_nullable_key = 1
        """

        ch_client.command(create_sql)
        logger.info(f"Table '{table_name}' created (ORDER BY `{pk_col}`).")
        # Invalidate column type cache so it's refreshed on next insert
        _column_type_cache.pop(table_name, None)
        return True

    except Exception as e:
        logger.error(f"Error creating table '{table_name}': {e}")
        return False


# ===========================================================================
#  Schema evolution (auto-add missing columns)
# ===========================================================================
def _infer_ch_type(value) -> str:
    """Infer a ClickHouse column type from a Python value."""
    if isinstance(value, bool):
        return "UInt8"
    elif isinstance(value, int):
        return "Int64"
    elif isinstance(value, float):
        return "Float64"
    elif isinstance(value, datetime):
        return "DateTime"
    else:
        return "String"


def _evolve_schema(ch_client, table_name: str, record: dict) -> bool:
    """
    Compare record keys against existing ClickHouse columns.
    Add any missing columns via ALTER TABLE ADD COLUMN.
    Returns True if evolution succeeded (or was unnecessary).
    """
    try:
        existing_cols = set(_get_column_types(ch_client, table_name).keys())
        record_cols = set(record.keys())
        missing_cols = record_cols - existing_cols

        if not missing_cols:
            logger.debug(f"No missing columns for '{table_name}'.")
            return True

        for col_name in missing_cols:
            ch_type = _infer_ch_type(record[col_name])
            alter_sql = f"ALTER TABLE `{table_name}` ADD COLUMN IF NOT EXISTS `{col_name}` Nullable({ch_type})"
            logger.info(f"Schema evolution: Adding column `{col_name}` Nullable({ch_type}) to '{table_name}'")
            ch_client.command(alter_sql)

        # Invalidate column type cache so next insert picks up new columns
        _column_type_cache.pop(table_name, None)
        return True

    except Exception as e:
        logger.error(f"Schema evolution failed for '{table_name}': {e}", exc_info=True)
        return False


# ===========================================================================
#  CDC event processing
# ===========================================================================
def process_cdc_event(ch_client, message: dict) -> bool:
    """
    Process a single validated CDC event and write to ClickHouse (mirroring mode).

    Assumes the message has already passed validate_cdc_message().
    """
    try:
        payload = message["payload"]
        operation = payload["op"]

        # Table name from Debezium source metadata
        source = payload.get("source", {})
        table_name = source.get("table", "unknown_table")

        # ----- DELETE --------------------------------------------------------
        if operation == "d":
            record = payload.get("before", {})
            if not record:
                logger.warning(f"DELETE event for '{table_name}' has no 'before' data. Skipping.")
                return True  # ACK anyway — nothing to delete

            id_val = record.get("id")
            if id_val is not None:
                try:
                    ch_client.command(f"DELETE FROM `{table_name}` WHERE id = {id_val}")
                    logger.info(f"DELETE: Removed id={id_val} from '{table_name}'.")
                except Exception:
                    try:
                        ch_client.command(f"ALTER TABLE `{table_name}` DELETE WHERE id = {id_val}")
                        logger.info(f"DELETE (mutation): Removed id={id_val} from '{table_name}'.")
                    except Exception as e:
                        logger.error(f"Failed to DELETE id={id_val} from '{table_name}': {e}")
                        return False
            else:
                logger.warning(f"DELETE event for '{table_name}' has no 'id'. Skipping physical delete.")
            return True

        # ----- UPDATE --------------------------------------------------------
        if operation == "u":
            after_record = payload.get("after", {})
            before_record = payload.get("before", {})
            id_val = before_record.get("id") or after_record.get("id") if before_record else after_record.get("id")

            # Mirror: delete old version, then insert new
            if id_val is not None:
                try:
                    ch_client.command(f"DELETE FROM `{table_name}` WHERE id = {id_val}")
                except Exception:
                    try:
                        ch_client.command(f"ALTER TABLE `{table_name}` DELETE WHERE id = {id_val}")
                    except Exception as e:
                        logger.warning(f"Could not delete old row id={id_val} from '{table_name}' before update: {e}")

            record = after_record
            operation_type = "UPDATE"

        # ----- CREATE / SNAPSHOT ---------------------------------------------
        elif operation in ("c", "r"):
            record = payload.get("after", {})
            operation_type = "INSERT" if operation == "c" else "SNAPSHOT"
        else:
            # Should never happen after validation, but keep as safety net
            logger.warning(f"Unexpected operation '{operation}'. Skipping.")
            return False

        if not record:
            logger.warning(f"No record data in '{operation_type}' event for '{table_name}'. Skipping.")
            return True  # ACK — nothing to insert

        # Coerce values (timestamps, etc.)
        coerced_record = {k: coerce_value(v) for k, v in record.items()}

        # Ensure ClickHouse table exists
        if not create_table_if_not_exists(ch_client, table_name, coerced_record):
            return False

        # Add CDC metadata columns
        coerced_record["_cdc_operation"] = operation_type
        coerced_record["_cdc_timestamp"] = parse_timestamp(payload.get("ts_ms", 0))

        # Insert into ClickHouse
        columns = list(coerced_record.keys())
        values = [coerced_record[col] for col in columns]

        # Cast values to match ClickHouse column types (prevents TypeError
        # when Debezium sends int for a String column or vice versa)
        values = _cast_row_for_table(ch_client, table_name, columns, values)

        try:
            ch_client.insert(table_name, [values], column_names=columns)
        except Exception as insert_err:
            if "Unrecognized column" in str(insert_err):
                # Schema evolution: source table has new columns not yet in ClickHouse.
                # Auto-add them and retry.
                logger.warning(f"Schema drift detected on '{table_name}'. Attempting auto-evolution...")
                if _evolve_schema(ch_client, table_name, coerced_record):
                    # Re-cast after schema change and retry insert
                    values = _cast_row_for_table(ch_client, table_name, columns, values)
                    ch_client.insert(table_name, [values], column_names=columns)
                    logger.info(f"Schema evolution succeeded for '{table_name}'. Insert retried OK.")
                else:
                    raise  # Re-raise if evolution failed
            else:
                raise  # Re-raise non-schema errors

        stats["processed"] += 1
        stats["last_processed"] = datetime.now().isoformat()

        if stats["processed"] % 100 == 0:
            logger.info(
                f"Progress: {stats['processed']} rows processed, "
                f"{stats['errors']} errors, {stats['heartbeats']} heartbeats skipped."
            )

        logger.debug(f"Inserted {operation_type} into '{table_name}' — record keys: {list(record.keys())}")
        return True

    except Exception as e:
        logger.error(f"Error processing CDC event: {e}", exc_info=True)
        stats["errors"] += 1
        return False



# ===========================================================================
#  Main consumer loop
# ===========================================================================
def consume_messages():
    """Main consumer loop with reconnection logic."""
    global running

    while running:
        connection = None
        try:
            logger.info(f"Connecting to RabbitMQ at {RABBITMQ_HOST}...")
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host=RABBITMQ_HOST,
                    credentials=credentials,
                    heartbeat=600,
                    blocked_connection_timeout=300,
                )
            )
            channel = connection.channel()

            # Declare queue (idempotent)
            channel.queue_declare(queue=QUEUE_NAME, durable=True)

            # Process one message at a time
            channel.basic_qos(prefetch_count=1)

            logger.info(f"Connected. Waiting for messages in '{QUEUE_NAME}'...")

            # ClickHouse client
            ch_client = get_clickhouse_client()

            def callback(ch, method, properties, body):
                """Process a single message from the queue."""
                try:
                    # -- Empty body -------------------------------------------
                    if not body:
                        logger.debug("Received empty message body. ACK and skip.")
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        return

                    decoded_body = body.decode("utf-8", errors="replace")

                    # -- Known junk -------------------------------------------
                    if decoded_body.strip().lower() == "default":
                        logger.debug("Skipping 'default' test message.")
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        return

                    # -- Parse JSON -------------------------------------------
                    try:
                        message = json.loads(body)
                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON: {e}. Body: {decoded_body[:200]}")
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                        return

                    # -- Heartbeat filter -------------------------------------
                    if is_heartbeat(message):
                        stats["heartbeats"] += 1
                        logger.debug(f"Heartbeat received (total: {stats['heartbeats']}). ACK.")
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        return

                    # -- Validate CDC structure --------------------------------
                    is_valid, reason = validate_cdc_message(message)
                    if not is_valid:
                        stats["skipped"] += 1
                        logger.warning(f"Invalid CDC message ({reason}). ACK and skip. Body: {decoded_body[:200]}")
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                        return

                    # -- Process the event ------------------------------------
                    success = process_cdc_event(ch_client, message)

                    if success:
                        ch.basic_ack(delivery_tag=method.delivery_tag)
                    else:
                        logger.warning(f"Processing failed. NACK with requeue=True for retry.")
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

                except Exception as e:
                    logger.error(f"Unexpected callback error: {e}", exc_info=True)
                    try:
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                    except Exception:
                        pass  # Channel may already be closed

            channel.basic_consume(queue=QUEUE_NAME, on_message_callback=callback)
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            logger.error(f"RabbitMQ connection error: {e}. Retrying in 5s...")
            time.sleep(5)
        except KeyboardInterrupt:
            logger.info("Interrupted by user.")
            running = False
        except Exception as e:
            logger.error(f"Unexpected error: {e}. Retrying in 5s...", exc_info=True)
            time.sleep(5)
        finally:
            if connection and connection.is_open:
                try:
                    connection.close()
                except Exception:
                    pass

    logger.info(
        f"Consumer stopped. "
        f"Processed: {stats['processed']}, Errors: {stats['errors']}, "
        f"Heartbeats: {stats['heartbeats']}, Skipped: {stats['skipped']}"
    )


# ===========================================================================
#  Entry point
# ===========================================================================
if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info("=" * 60)
    logger.info("RabbitMQ → ClickHouse CDC Consumer (v2.0)")
    logger.info("=" * 60)

    consume_messages()

    logger.info("Consumer exited cleanly.")
    sys.exit(0)
