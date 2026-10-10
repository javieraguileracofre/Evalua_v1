# services/platform/schema_version.py
from db.schema_revision import (
    ERP_SCHEMA_REVISION,
    registry_schema_matches,
    runtime_schema_version,
    schema_is_current,
)

__all__ = [
    "ERP_SCHEMA_REVISION",
    "registry_schema_matches",
    "runtime_schema_version",
    "schema_is_current",
]
