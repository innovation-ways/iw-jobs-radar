"""SQL helpers that make tables append-only (ADR-030).

Immutable tables (revisions, snapshots, extractions, evaluations, events) reject ``UPDATE`` and
``DELETE`` through a database trigger. The audited deletion procedure (UC-08) is the only
supported bypass: it runs ``SET LOCAL jobs_radar.allow_mutation = 'on'`` inside its transaction.
"""

FORBID_MUTATION_FUNCTION = """
CREATE OR REPLACE FUNCTION jobs_radar_forbid_mutation() RETURNS trigger AS $$
BEGIN
    IF current_setting('jobs_radar.allow_mutation', true) = 'on' THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'table % is append-only: % is not allowed', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
"""

DROP_FORBID_MUTATION_FUNCTION = "DROP FUNCTION IF EXISTS jobs_radar_forbid_mutation();"


def append_only_trigger_name(table: str) -> str:
    """Return the trigger name used for ``table``."""
    return f"trg_{table}_append_only"


def create_append_only_trigger(table: str) -> str:
    """Return the DDL that makes ``table`` append-only.

    The table name must be a trusted constant (migrations and tests only), never user input.
    """
    name = append_only_trigger_name(table)
    return (
        f"CREATE TRIGGER {name} BEFORE UPDATE OR DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION jobs_radar_forbid_mutation();"
    )


def drop_append_only_trigger(table: str) -> str:
    """Return the DDL that removes the append-only trigger from ``table``."""
    return f"DROP TRIGGER IF EXISTS {append_only_trigger_name(table)} ON {table};"
