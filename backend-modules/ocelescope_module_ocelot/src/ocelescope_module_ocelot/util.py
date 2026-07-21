import math

from ocelescope import OCEL
from ocelescope.ocel.constants.pm4py import (
    ACTIVITY_COL,
    E2O_EVENT_ID,
    E2O_OBJECT_ID,
    E2O_QUALIFIER,
    EID_COL,
    O2O_QUALIFIER,
    O2O_SOURCE_ID,
    O2O_TARGET_ID,
    OID_COL,
    OTYPE_COL,
    TIMESTAMP_COL,
)
from ocelescope.ocel.constants.tables import (
    E2O_TABLE,
    EVENTS_TABLE,
    O2O_TABLE,
    OBJECTS_TABLE,
)
from ocelescope.util.sql import ident

from ocelescope_module_ocelot.models import (
    EntityTableColumn,
    OcelEntity,
    PaginatedResponse,
)

TOTAL_COL = "@@total"


def _relation_key(relation_qualifier: str) -> str:
    """SQL for a relation's key: ``ObjectType`` or ``ObjectType (qualifier)``.

    The related object's type always carries the key, so qualifiers that share a
    name across types stay apart -- and an unqualified edge still lands under a
    key of its own. Expects the relation table aliased ``r`` and the joined
    objects table aliased ``o``.
    """
    return (
        f"o.{ident(OTYPE_COL)} "
        f"|| coalesce(' (' || nullif(r.{ident(relation_qualifier)}, '') || ')', '')"
    )


def _paginate(
    ocel: OCEL,
    *,
    table: str,
    id_col: str,
    filter_col: str,
    filter_value: str,
    base_cols: list[str],
    relation_table: str,
    relation_source: str,
    relation_target: str,
    relation_qualifier: str,
    page: int,
    page_size: int,
    sort_by: str | None,
    descending: bool,
) -> PaginatedResponse:
    """Page one entity table and attach each row's outgoing relations.

    One query: the page is cut first, its total comes from a window function,
    and only that page's relations are joined into a ``key -> [related ids]``
    map, keyed by the related object's type and its qualifier (see
    ``_relation_key``). Aggregating after the LIMIT is what keeps the relation
    table's many-to-many fan-out from multiplying the page's rows -- and it lets
    DuckDB push the page's ids into the relation scan as a dynamic filter, so
    the relation table is never grouped as a whole.
    """
    order = f"{ident(sort_by or base_cols[-1])}{' DESC' if descending else ''}"

    query = f"""
        WITH page AS (
            SELECT *, count(*) OVER () AS {ident(TOTAL_COL)}
            FROM {table}
            WHERE {ident(filter_col)} = ?
            ORDER BY {order}
            LIMIT ? OFFSET ?
        ),
        edges AS (
            SELECT r.{ident(relation_source)} AS id,
                   {_relation_key(relation_qualifier)} AS key,
                   list(r.{ident(relation_target)}) AS ids
            FROM {relation_table} r
            JOIN page p ON r.{ident(relation_source)} = p.{ident(id_col)}
            LEFT JOIN {OBJECTS_TABLE} o ON r.{ident(relation_target)} = o.{ident(OID_COL)}
            GROUP BY 1, 2
        ),
        relations AS (
            SELECT id, map_from_entries(list({{k: key, v: ids}})) AS relations
            FROM edges
            WHERE key IS NOT NULL
            GROUP BY id
        )
        SELECT p.*, r.relations
        FROM page p
        LEFT JOIN relations r ON p.{ident(id_col)} = r.id
        ORDER BY p.{order}
    """

    rel = ocel.sql(query, params=[filter_value, page_size, (page - 1) * page_size])
    columns = rel.columns
    rows = rel.fetchall()

    at = {name: i for i, name in enumerate(columns)}
    total = int(rows[0][at[TOTAL_COL]]) if rows else 0

    reserved = {*base_cols, TOTAL_COL, "relations"}
    attribute_cols = [(name, at[name]) for name in columns if name not in reserved]
    time_idx = at[TIMESTAMP_COL] if TIMESTAMP_COL in base_cols else None

    items = [
        OcelEntity(
            id=row[at[id_col]],
            attributes={
                name: row[i] for name, i in attribute_cols if row[i] is not None
            },
            relations=row[at["relations"]] or {},
            timestamp=row[time_idx] if time_idx is not None else None,
        )
        for row in rows
    ]

    return PaginatedResponse(
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if page_size else 0,
        total_items=total,
        items=items,
    )


def _column_defs(
    ocel: OCEL,
    *,
    table: str,
    id_col: str,
    filter_col: str,
    filter_value: str,
    base_cols: list[str],
    relation_table: str,
    relation_source: str,
    relation_target: str,
    relation_qualifier: str,
) -> list[EntityTableColumn]:
    """Describe the columns a page of this entity type will actually fill.

    Two queries, both scoped to ``filter_value``:

    * the relation keys reachable from this type -- built with the *same*
      ``_relation_key`` expression ``_paginate`` uses, so every accessor here is
      guaranteed to be a key in ``OcelEntity.relations``
    * the attribute columns that are non-NULL for at least one row, since the
      entity table is wide across all types and most columns will be empty
    """
    relation_key = _relation_key(relation_qualifier)
    relation_rows = ocel.sql(
        f"""
        SELECT DISTINCT {relation_key} AS key
        FROM {relation_table} r
        JOIN {table} e ON r.{ident(relation_source)} = e.{ident(id_col)}
        LEFT JOIN {OBJECTS_TABLE} o ON r.{ident(relation_target)} = o.{ident(OID_COL)}
        WHERE e.{ident(filter_col)} = ? AND {relation_key} IS NOT NULL
        ORDER BY key
        """,
        params=[filter_value],
    ).fetchall()

    relation_columns = [
        EntityTableColumn(accessor=key, type="relation") for (key,) in relation_rows
    ]

    candidates = [
        c
        for c in ocel.sql(f"SELECT * FROM {table} LIMIT 0").columns
        if c not in base_cols
    ]
    attribute_columns: list[EntityTableColumn] = []
    if candidates:
        counts = ocel.sql(
            "SELECT "
            + ", ".join(f"count({ident(c)})" for c in candidates)
            + f" FROM {table} WHERE {ident(filter_col)} = ?",
            params=[filter_value],
        ).fetchone()
        attribute_columns = [
            EntityTableColumn(accessor=name, type="attribute")
            for name, filled in zip(candidates, counts or ())
            if filled
        ]

    leading = [EntityTableColumn(accessor="id", type="attribute", title="#")]
    if TIMESTAMP_COL in base_cols:
        leading.append(
            EntityTableColumn(accessor="timestamp", type="attribute", title="Timestamp")
        )

    return [*leading, *attribute_columns, *relation_columns]


def get_object_columns_def(
    ocel: OCEL,
    object_type: str,
) -> list[EntityTableColumn]:
    """Columns for a ``paginate_objects(ocel, object_type)`` table."""
    return _column_defs(
        ocel,
        table=OBJECTS_TABLE,
        id_col=OID_COL,
        filter_col=OTYPE_COL,
        filter_value=object_type,
        base_cols=[OTYPE_COL, OID_COL],
        relation_table=O2O_TABLE,
        relation_source=O2O_SOURCE_ID,
        relation_target=O2O_TARGET_ID,
        relation_qualifier=O2O_QUALIFIER,
    )


def get_activity_columns_def(
    ocel: OCEL,
    activity_name: str,
) -> list[EntityTableColumn]:
    """Columns for a ``paginate_events(ocel, activity_name)`` table."""
    return _column_defs(
        ocel,
        table=EVENTS_TABLE,
        id_col=EID_COL,
        filter_col=ACTIVITY_COL,
        filter_value=activity_name,
        base_cols=[ACTIVITY_COL, EID_COL, TIMESTAMP_COL],
        relation_table=E2O_TABLE,
        relation_source=E2O_EVENT_ID,
        relation_target=E2O_OBJECT_ID,
        relation_qualifier=E2O_QUALIFIER,
    )


def paginate_objects(
    ocel: OCEL,
    object_type: str,
    page: int = 1,
    page_size: int = 10,
    sort_by: str | None = None,
    descending: bool = False,
) -> PaginatedResponse:
    """One page of ``object_type`` objects, each with its related objects (O2O).

    Only outgoing edges are followed -- those where the object is O2O_SOURCE_ID.
    An edge stored the other way round (``Truck -> Container``) does not show up
    on the Container. Sorts by ``ocel:oid`` unless told otherwise.
    """
    return _paginate(
        ocel,
        table=OBJECTS_TABLE,
        id_col=OID_COL,
        filter_col=OTYPE_COL,
        filter_value=object_type,
        base_cols=[OTYPE_COL, OID_COL],
        relation_table=O2O_TABLE,
        relation_source=O2O_SOURCE_ID,
        relation_target=O2O_TARGET_ID,
        relation_qualifier=O2O_QUALIFIER,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        descending=descending,
    )


def paginate_events(
    ocel: OCEL,
    activity: str,
    page: int = 1,
    page_size: int = 10,
    sort_by: str | None = None,
    descending: bool = False,
) -> PaginatedResponse:
    """One page of ``activity`` events, each with its related objects (E2O).

    E2O is inherently directed event -> object, so unlike O2O there is no edge
    orientation to choose. Sorts by ``ocel:timestamp`` unless told otherwise.
    """
    return _paginate(
        ocel,
        table=EVENTS_TABLE,
        id_col=EID_COL,
        filter_col=ACTIVITY_COL,
        filter_value=activity,
        base_cols=[ACTIVITY_COL, EID_COL, TIMESTAMP_COL],
        relation_table=E2O_TABLE,
        relation_source=E2O_EVENT_ID,
        relation_target=E2O_OBJECT_ID,
        relation_qualifier=E2O_QUALIFIER,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        descending=descending,
    )
