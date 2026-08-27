import json
import logging
import re

_SAFE_EXCEPTION_VALUE = re.compile(r"[A-Za-z][A-Za-z0-9_.]{0,63}").fullmatch
_EXCEPTION_FIELDS = ("exception_class", "exception_code")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        exception_type = record.exc_info[0] if record.exc_info else None
        if exception_type is not None:
            payload["exception_class"] = exception_type.__name__
        for field in _EXCEPTION_FIELDS:
            value = getattr(record, field, None)
            if isinstance(value, str) and _SAFE_EXCEPTION_VALUE(value):
                payload[field] = value
        return json.dumps(payload, ensure_ascii=False)
