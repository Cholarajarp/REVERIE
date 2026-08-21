import logging
import json
import sys
import os
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, Dict, Any

# OpenTelemetry distributed tracing setup
try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.gcp_trace import CloudTraceSpanExporter
    
    provider = TracerProvider()
    try:
        exporter = CloudTraceSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(exporter))
    except Exception:
        # Fallback if GCP Trace API is unreachable in local dev
        pass
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("reverie.tracer")
except Exception:
    trace = None
    tracer = None

@contextmanager
def trace_span(name: str, attributes: Optional[Dict[str, Any]] = None):
    """Context manager to create OpenTelemetry spans and attach structured telemetry attributes."""
    if tracer and trace:
        with tracer.start_as_current_span(name) as span:
            if attributes:
                for k, v in attributes.items():
                    span.set_attribute(str(k), str(v) if not isinstance(v, (int, float, bool)) else v)
            yield span
    else:
        yield None

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
            
        # Inject OpenTelemetry trace_id and span_id for Google Cloud Logging end-to-end tracing
        if trace:
            try:
                current_span = trace.get_current_span()
                if current_span:
                    span_context = current_span.get_span_context()
                    if span_context and span_context.is_valid:
                        trace_id_hex = f"{span_context.trace_id:032x}"
                        span_id_hex = f"{span_context.span_id:016x}"
                        
                        project_id = os.getenv("GOOGLE_CLOUD_PROJECT", "reverie-project")
                        log_record["logging.googleapis.com/trace"] = f"projects/{project_id}/traces/{trace_id_hex}"
                        log_record["logging.googleapis.com/spanId"] = span_id_hex
                        log_record["trace_id"] = trace_id_hex
                        log_record["span_id"] = span_id_hex
            except Exception:
                pass
                    
        # Include extra attributes if passed in logger calls
        for attr in ["action", "user_id", "scene_id", "character", "drama_score"]:
            if hasattr(record, attr):
                log_record[attr] = getattr(record, attr)
            
        return json.dumps(log_record)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)
        logger.propagate = False
    return logger
