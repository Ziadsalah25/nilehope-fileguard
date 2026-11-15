"""Validate optional cross-platform metadata; never interpret observations as enforcement."""

import math

FIELDS = {
    "os_family": "VARCHAR(16) NOT NULL DEFAULT 'unknown'",
    "os_version": "VARCHAR(160)",
    "architecture": "VARCHAR(32)",
    "cpu_percent": "REAL",
    "memory_total_mb": "BIGINT",
    "memory_used_mb": "BIGINT",
    "disk_total_mb": "BIGINT",
    "disk_used_mb": "BIGINT",
    "uptime_seconds": "BIGINT",
    "telemetry_at": "TEXT",
    "monitoring_status": "VARCHAR(20) NOT NULL DEFAULT 'unknown'",
    "monitoring_message": "TEXT",
}


def validate(body):
    result = {}
    family = body.get("os_family")
    if family is not None:
        if family not in ("windows", "linux", "unknown"):
            raise ValueError("os_family must be windows, linux, or unknown")
        result["os_family"] = family
    for field, maximum in (
        ("os_version", 160),
        ("architecture", 32),
        ("monitoring_message", 1000),
    ):
        if body.get(field) is not None:
            result[field] = str(body[field])[:maximum]
    status = body.get("monitoring_status")
    if status is not None:
        # Recovery workers distinguish startup and degraded protection locally.
        if isinstance(status, str):
            status = {"starting": "waiting", "degraded": "partial"}.get(status, status)
        if status not in ("healthy", "partial", "waiting", "unknown"):
            raise ValueError("Invalid monitoring_status")
        result["monitoring_status"] = status
    for field in (
        "cpu_percent",
        "memory_total_mb",
        "memory_used_mb",
        "disk_total_mb",
        "disk_used_mb",
        "uptime_seconds",
    ):
        value = body.get(field)
        if value is None:
            continue
        if (
            isinstance(value, bool)
            or not isinstance(value, (float, int))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{field} must be a finite number")
        if value < 0 or value > (100 if field == "cpu_percent" else 2**63 - 1):
            raise ValueError(f"{field} is out of range")
        result[field] = round(value, 1) if field == "cpu_percent" else int(value)
    for prefix in ("memory", "disk"):
        if result.get(prefix + "_used_mb", 0) > result.get(
            prefix + "_total_mb", 2**63 - 1
        ):
            raise ValueError(f"{prefix} usage cannot exceed total")
    if any(
        key in result
        for key in ("cpu_percent", "memory_total_mb", "disk_total_mb", "uptime_seconds")
    ):
        from .audit import now

        result["telemetry_at"] = now()
    return result
