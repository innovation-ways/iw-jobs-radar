"""SQL helpers that make tables append-only (ADR-030).

The SQL constants below are imported by migrations 0001 and 0002 and are therefore FROZEN: to change
trigger behaviour, add a new migration that runs ``CREATE OR REPLACE FUNCTION`` instead of editing
them here.


Immutable tables (revisions, snapshots, extractions, evaluations, events) reject ``UPDATE`` and
``DELETE`` through a database trigger. The audited deletion procedure (UC-08) is the only
supported bypass: it runs ``SET LOCAL jobs_radar.allow_mutation = 'on'`` inside its transaction.
"""

# Tables that reject every UPDATE and DELETE (outside the audited deletion procedure).
APPEND_ONLY_TABLES: tuple[str, ...] = (
    "profile_revision",
    "intent_revision",
    "evidence",
    "job_snapshot",
    "job_change_event",
    "match_evaluation",
    "score_dimension",
    "inbox_event",
    "source_run_result",
    "audit_event",
)

# Tables whose rows may change while ``status = 'pending'`` and are immutable once finalised.
CONDITIONALLY_IMMUTABLE_TABLES: tuple[str, ...] = ("job_extraction",)

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

# Queue-like rows (AI extractions) are created as 'pending' and updated exactly once to a final
# status; after that they are immutable, like the append-only tables.
FORBID_FINAL_MUTATION_FUNCTION = """
CREATE OR REPLACE FUNCTION jobs_radar_forbid_final_mutation() RETURNS trigger AS $$
BEGIN
    IF current_setting('jobs_radar.allow_mutation', true) = 'on' THEN
        IF TG_OP = 'DELETE' THEN
            RETURN OLD;
        END IF;
        RETURN NEW;
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.status = 'pending' THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'table % rows are immutable once finalised: % is not allowed',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'integrity_constraint_violation';
END;
$$ LANGUAGE plpgsql;
"""

DROP_FORBID_FINAL_MUTATION_FUNCTION = "DROP FUNCTION IF EXISTS jobs_radar_forbid_final_mutation();"


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


def create_final_mutation_trigger(table: str) -> str:
    """Return the DDL that makes ``table`` immutable once its ``status`` leaves ``pending``."""
    return (
        f"CREATE TRIGGER trg_{table}_immutable_when_final BEFORE UPDATE OR DELETE ON {table} "
        "FOR EACH ROW EXECUTE FUNCTION jobs_radar_forbid_final_mutation();"
    )
