import {
  LoadingOverlay,
  Scroller,
  Stack,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import { useEventCounts, useObjectCounts } from "@ocelescope/api-base";

import EntityTable from "./EntityTable";

const EntityPage: React.FC<{
  ocelId: string;
  type: "events" | "objects";
  title?: string;
  description?: string;
}> = ({ ocelId, type, title, description }) => {
  const areEntitiesEvents = type === "events";

  const { data: entityCounts, isLoading } = (
    areEntitiesEvents ? useEventCounts : useObjectCounts
  )(ocelId);

  return (
    <Stack gap={"xs"} p={"xs"} pos={"relative"} h={"100%"}>
      {title && <Title order={2}>{title}</Title>}
      {description && (
        <Text c="dimmed" size="sm" mb="xs">
          {description}
        </Text>
      )}
      {entityCounts && (
        <Tabs
          keepMounted={false}
          defaultValue={Object.keys(entityCounts)[0]}
          flex={1}
          mih={0}
          display={"flex"}
          style={{ flexDirection: "column" }}
        >
          <Tabs.List>
            <Scroller>
              {Object.entries(entityCounts ?? {}).map(([entityName, count]) => (
                <Tabs.Tab key={entityName} value={entityName}>
                  {entityName} ({count})
                </Tabs.Tab>
              ))}
            </Scroller>
          </Tabs.List>
          {Object.keys(entityCounts).map((entityName) => (
            <Tabs.Panel
              key={entityName}
              value={entityName}
              pos={"relative"}
              flex={1}
              mih={0}
            >
              <EntityTable
                type={type}
                ocelId={ocelId}
                entityName={entityName}
              />
            </Tabs.Panel>
          ))}
        </Tabs>
      )}
      <LoadingOverlay visible={isLoading} />
    </Stack>
  );
};

export default EntityPage;
