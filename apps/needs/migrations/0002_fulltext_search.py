"""§10.4 — generated tsvector columns + GIN indexes on needs_need and
offers_offer (one migration, both tables; the offers dependency below makes
the ordering explicit).

Postgres-only by vendor guard; reversible; idempotent (IF NOT EXISTS).
Renumber + repoint dependencies if needs has migrations beyond 0001.
"""
from django.db import migrations

TABLES = (
    ("needs_need", "needs_need_fts_idx"),
    ("offers_offer", "offers_offer_fts_idx"),
)

ADD_SQL = """
ALTER TABLE "{table}" ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (
        to_tsvector('english',
            coalesce(title, '') || ' ' || coalesce(description, ''))
    ) STORED
"""

INDEX_SQL = 'CREATE INDEX IF NOT EXISTS "{index}" ON "{table}" USING GIN (search_vector)'


def add_fts(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, index in TABLES:
        schema_editor.execute(ADD_SQL.format(table=table))
        schema_editor.execute(INDEX_SQL.format(index=index, table=table))


def drop_fts(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    for table, index in TABLES:
        schema_editor.execute(f'DROP INDEX IF EXISTS "{index}"')
        schema_editor.execute(
            f'ALTER TABLE "{table}" DROP COLUMN IF EXISTS search_vector')


class Migration(migrations.Migration):

    dependencies = [
        ("needs", "0001_initial"),
        ("offers", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_fts, drop_fts),
    ]
