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
    OBJECT_CHANGED_FIELD,
    OID_COL,
    OTYPE_COL,
    TIMESTAMP_COL,
)
from ocelescope.ocel.constants.tables import (
    E2O_TABLE,
    EVENTS_TABLE,
    O2O_TABLE,
    OBJECT_CHANGES_TABLE,
    OBJECTS_TABLE,
)
from ocelescope.util.sql import ident

from ocelescope_module_ocelot.models import (
    EntityTableColumn,
    OcelEntity,
    PaginatedResponse,
)

TOTAL_COL = "@@total"

OBJECT_COLS = [OTYPE_COL, OID_COL]
EVENT_COLS = [ACTIVITY_COL, EID_COL, TIMESTAMP_COL]


def _relation_key(relation_qualifier: str) -> str:
    """SQL for a relation's key: ``ObjectType`` or ``ObjectType (qualifier)``.

    The related object's type always carries the key, so qualifiers that share a
    name across types stay apart -- and an unqualified edge still lands under a
    key of its own. Expects the relation table aliased ``r`` and the joined
    objects table aliased ``o``. Both the page queries and the column
    definitions build their keys with it, so every column an entity table
    announces is a key its rows can actually carry.
    """
    return (
        f"o.{ident(OTYPE_COL)} "
        f"|| coalesce(' (' || nullif(r.{ident(relation_qualifier)}, '') || ')', '')"
    )


def _response(
    ocel: OCEL,
    query: str,
    params: list[object],
    *,
    id_col: str,
    base_cols: list[str],
    page: int,
    page_size: int,
) -> PaginatedResponse:
    """Run a page query and read its rows back as entities.

    A page query returns the entity's own columns, one column per attribute, a
    ``relations`` map and -- from a window function over the rows the page was
    cut from -- the total. Everything that is not a column of the entity table
    itself is read back as an attribute, so an entity carrying its attributes in
    columns and one whose attributes were folded in from the change table decode
    the same way.
    """
    rows = ocel.sql(query, params=params)
    columns = rows.columns
    values = rows.fetchall()

    at = {name: i for i, name in enumerate(columns)}
    total = int(values[0][at[TOTAL_COL]]) if values else 0

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
        for row in values
    ]

    return PaginatedResponse(
        page=page,
        page_size=page_size,
        total_pages=math.ceil(total / page_size) if page_size else 0,
        total_items=total,
        items=items,
    )


def paginate_objects(
    ocel: OCEL,
    object_type: str,
    page: int = 1,
    page_size: int = 10,
    sort_by: str | None = None,
    descending: bool = False,
) -> PaginatedResponse:
    """One page of ``object_type`` objects, each with its attributes and O2O relations.

    Only outgoing edges are followed -- those where the object is O2O_SOURCE_ID.
    An edge stored the other way round (``Truck -> Container``) does not show up
    on the Container. Sorts by ``ocel:oid`` unless told otherwise.

    An object keeps its attributes in the change table, one value per row, so
    ``attributes`` folds them back into one row per object: ``any_value`` skips
    NULLs and a change row holds a value in one column only, so ordering the
    aggregate by time picks out each attribute's earliest value -- what the
    object was first known to hold, which is the value the objects table itself
    used to carry. The fold has to come before the page is cut, since the page
    may be ordered by one of the folded values.

    Relations are aggregated after the cut, though: that keeps the many-to-many
    fan-out from multiplying the page's rows, and it lets DuckDB push the page's
    ids into the relation scan as a dynamic filter, so O2O is never grouped as a
    whole.
    """
    key = ident(OID_COL)
    order = f"{ident(sort_by or OID_COL)}{' DESC' if descending else ''}"

    # one fold per attribute the change table carries, its own bookkeeping aside
    meta = {OID_COL, TIMESTAMP_COL, OBJECT_CHANGED_FIELD}
    attributes = [
        c
        for c in ocel.sql(f"SELECT * FROM {OBJECT_CHANGES_TABLE} LIMIT 0").columns
        if c not in meta
    ]
    fold = ",\n                   any_value(c.{0} ORDER BY c.{1}) AS {0}"
    folds = "".join(fold.format(ident(a), ident(TIMESTAMP_COL)) for a in attributes)
    folded = "".join(f", a.{ident(a)}" for a in attributes)

    query = f"""
        WITH scope AS (
            SELECT * FROM {OBJECTS_TABLE}
            WHERE {ident(OTYPE_COL)} = ?
        ),
        attributes AS (
            SELECT c.{key} AS id{folds}
            FROM {OBJECT_CHANGES_TABLE} c
            JOIN scope s ON c.{key} = s.{key}
            GROUP BY 1
        ),
        page AS (
            SELECT s.*{folded}, count(*) OVER () AS {ident(TOTAL_COL)}
            FROM scope s
            LEFT JOIN attributes a ON s.{key} = a.id
            ORDER BY {order}
            LIMIT ? OFFSET ?
        ),
        edges AS (
            SELECT r.{ident(O2O_SOURCE_ID)} AS id,
                   {_relation_key(O2O_QUALIFIER)} AS key,
                   list(r.{ident(O2O_TARGET_ID)}) AS ids
            FROM {O2O_TABLE} r
            JOIN page p ON r.{ident(O2O_SOURCE_ID)} = p.{key}
            LEFT JOIN {OBJECTS_TABLE} o ON r.{ident(O2O_TARGET_ID)} = o.{key}
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
        LEFT JOIN relations r ON p.{key} = r.id
        ORDER BY p.{order}
    """

    return _response(
        ocel,
        query,
        [object_type, page_size, (page - 1) * page_size],
        id_col=OID_COL,
        base_cols=OBJECT_COLS,
        page=page,
        page_size=page_size,
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

    An event carries its attributes in columns of its own, so the page is simply
    cut -- its total taken from a window function over the rows it was cut from
    -- and only that page's relations are aggregated. Grouping E2O against the
    page rather than as a whole keeps the fan-out from multiplying the page's
    rows and lets DuckDB push the page's ids into the relation scan.
    """
    key = ident(EID_COL)
    order = f"{ident(sort_by or TIMESTAMP_COL)}{' DESC' if descending else ''}"

    query = f"""
        WITH page AS (
            SELECT *, count(*) OVER () AS {ident(TOTAL_COL)}
            FROM {EVENTS_TABLE}
            WHERE {ident(ACTIVITY_COL)} = ?
            ORDER BY {order}
            LIMIT ? OFFSET ?
        ),
        edges AS (
            SELECT r.{ident(E2O_EVENT_ID)} AS id,
                   {_relation_key(E2O_QUALIFIER)} AS key,
                   list(r.{ident(E2O_OBJECT_ID)}) AS ids
            FROM {E2O_TABLE} r
            JOIN page p ON r.{ident(E2O_EVENT_ID)} = p.{key}
            LEFT JOIN {OBJECTS_TABLE} o ON r.{ident(E2O_OBJECT_ID)} = o.{ident(OID_COL)}
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
        LEFT JOIN relations r ON p.{key} = r.id
        ORDER BY p.{order}
    """

    return _response(
        ocel,
        query,
        [activity, page_size, (page - 1) * page_size],
        id_col=EID_COL,
        base_cols=EVENT_COLS,
        page=page,
        page_size=page_size,
    )


def get_object_columns_def(
    ocel: OCEL,
    object_type: str,
) -> list[EntityTableColumn]:
    """Columns a ``paginate_objects(ocel, object_type)`` table will actually fill.

    The attribute names come from the change rows' own ``ocel:field``: the names
    present for this type are read off one column rather than counted across
    every attribute the log has.
    """
    attributes = ocel.sql(
        f"""
        SELECT DISTINCT c.{ident(OBJECT_CHANGED_FIELD)} AS name
        FROM {OBJECT_CHANGES_TABLE} c
        JOIN {OBJECTS_TABLE} e ON c.{ident(OID_COL)} = e.{ident(OID_COL)}
        WHERE e.{ident(OTYPE_COL)} = ?
        ORDER BY name
        """,
        params=[object_type],
    ).fetchall()

    relation_key = _relation_key(O2O_QUALIFIER)
    relations = ocel.sql(
        f"""
        SELECT DISTINCT {relation_key} AS key
        FROM {O2O_TABLE} r
        JOIN {OBJECTS_TABLE} e ON r.{ident(O2O_SOURCE_ID)} = e.{ident(OID_COL)}
        LEFT JOIN {OBJECTS_TABLE} o ON r.{ident(O2O_TARGET_ID)} = o.{ident(OID_COL)}
        WHERE e.{ident(OTYPE_COL)} = ? AND {relation_key} IS NOT NULL
        ORDER BY key
        """,
        params=[object_type],
    ).fetchall()

    return [
        EntityTableColumn(accessor="id", type="attribute", title="#"),
        *(EntityTableColumn(accessor=name, type="attribute") for (name,) in attributes),
        *(EntityTableColumn(accessor=key, type="relation") for (key,) in relations),
    ]


def get_activity_columns_def(
    ocel: OCEL,
    activity_name: str,
) -> list[EntityTableColumn]:
    """Columns a ``paginate_events(ocel, activity_name)`` table will actually fill.

    An event's attributes are columns of the events table, which is wide across
    all activities, so the ones that stay empty for this activity are counted
    out: only a column non-NULL for at least one of its events is announced.
    """
    candidates = [
        c
        for c in ocel.sql(f"SELECT * FROM {EVENTS_TABLE} LIMIT 0").columns
        if c not in EVENT_COLS
    ]

    attributes: list[str] = []
    if candidates:
        counts = ocel.sql(
            "SELECT "
            + ", ".join(f"count({ident(c)})" for c in candidates)
            + f" FROM {EVENTS_TABLE} WHERE {ident(ACTIVITY_COL)} = ?",
            params=[activity_name],
        ).fetchone()
        attributes = [name for name, filled in zip(candidates, counts or ()) if filled]

    relation_key = _relation_key(E2O_QUALIFIER)
    relations = ocel.sql(
        f"""
        SELECT DISTINCT {relation_key} AS key
        FROM {E2O_TABLE} r
        JOIN {EVENTS_TABLE} e ON r.{ident(E2O_EVENT_ID)} = e.{ident(EID_COL)}
        LEFT JOIN {OBJECTS_TABLE} o ON r.{ident(E2O_OBJECT_ID)} = o.{ident(OID_COL)}
        WHERE e.{ident(ACTIVITY_COL)} = ? AND {relation_key} IS NOT NULL
        ORDER BY key
        """,
        params=[activity_name],
    ).fetchall()

    return [
        EntityTableColumn(accessor="id", type="attribute", title="#"),
        EntityTableColumn(accessor="timestamp", type="attribute", title="Timestamp"),
        *(EntityTableColumn(accessor=name, type="attribute") for name in attributes),
        *(EntityTableColumn(accessor=key, type="relation") for (key,) in relations),
    ]
