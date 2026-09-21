import {
  DataTable,
  type DataTableColumn,
  type DataTableSortStatus,
} from "mantine-datatable";
import { useMemo, useState } from "react";
import {
  useActivityColumns,
  useObjectColumns,
  usePaginatedEvents,
  usePaginatedObjects,
} from "../api/base";
import { keepPreviousData } from "@tanstack/react-query";
import { LoadingOverlay } from "@mantine/core";

const EntityTable: React.FC<{
  type: "events" | "objects";
  entityName: string;
  ocelId: string;
}> = ({ type, ocelId, entityName }) => {
  const areEntitiesEvents = type === "events";

  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<DataTableSortStatus | undefined>(undefined);

  const [pageSize, setPageSize] = useState(20);

  const { data: entities } = (
    areEntitiesEvents ? usePaginatedEvents : usePaginatedObjects
  )(
    ocelId,
    {
      type: entityName,
      page_size: pageSize,
      page,
      ...(sort && {
        sort_by: sort.columnAccessor,
        ascending: sort.direction === "asc",
      }),
    },
    {
      query: {
        placeholderData: keepPreviousData,
        staleTime: 5000,
      },
    },
  );

  const { data: columns = [] } = (
    areEntitiesEvents ? useActivityColumns : useObjectColumns
  )(ocelId, { type_name: entityName });

  const records = useMemo(
    () =>
      entities?.items.map((entity) => ({
        ...entity,
        ...entity.attributes,
        ...Object.assign(
          {},
          ...Object.entries(entity.relations).map(
            ([qualifierName, entityIds]) => ({
              [qualifierName]: entityIds.join(", "),
            }),
          ),
        ),
      })),
    [entities],
  );

  const transformedColumns: DataTableColumn[] = useMemo(
    () =>
      columns.map((column) => ({
        ...column,
        render: (record) => record[column.accessor] as React.ReactNode,
        sortable: column.type === "attribute",
      })),
    [columns],
  );

  return entities ? (
    <DataTable
      height={"100%"}
      page={entities.page}
      totalRecords={entities.total_items}
      recordsPerPage={entities.page_size}
      onPageChange={setPage}
      withColumnBorders
      columns={transformedColumns}
      records={records}
      recordsPerPageOptions={[20, 40, 50]}
      onRecordsPerPageChange={setPageSize}
      sortStatus={sort ?? { columnAccessor: "id", direction: "asc" }}
      onSortStatusChange={setSort}
    />
  ) : (
    <LoadingOverlay visible />
  );
};

export default EntityTable;
