import {
  ActionIcon,
  Autocomplete,
  Group,
  LoadingOverlay,
  Popover,
  Scroller,
  Stack,
  Tabs,
  Text,
  Title,
} from "@mantine/core";
import { useEventCounts, useObjectCounts } from "@ocelescope/api-base";

import EntityTable from "./EntityTable";
import { useDisclosure } from "@mantine/hooks";
import { useMemo, useState } from "react";
import { SearchIcon } from "lucide-react";

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

  const [activeTab, setActiveTab] = useState<string | null>(null);
  const [searchOpened, { close: closeSearch, toggle: toggleSearch }] =
    useDisclosure(false);

  const entityNames = useMemo(
    () => Object.keys(entityCounts ?? []),
    [entityCounts],
  );

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
          value={activeTab ?? entityNames[0]}
          onChange={setActiveTab}
          flex={1}
          mih={0}
          display={"flex"}
          style={{ flexDirection: "column" }}
        >
          <Group wrap="nowrap" gap="0" style={{ flexShrink: 0 }}>
            <Popover
              width={300}
              position="bottom-start"
              withArrow
              shadow="md"
              opened={searchOpened}
              onChange={closeSearch}
              trapFocus
              returnFocus
            >
              <Popover.Target>
                <ActionIcon
                  size={"lg"}
                  h={"100%"}
                  onClick={toggleSearch}
                  aria-label={`Search ${type} types`}
                  bdrs={0}
                >
                  <SearchIcon size={16} />
                </ActionIcon>
              </Popover.Target>
              <Popover.Dropdown>
                <Autocomplete
                  data={entityNames}
                  aria-label={`${type} type`}
                  placeholder={`Search ${type} types`}
                  selectFirstOptionOnChange
                  comboboxProps={{ withinPortal: false }}
                  onOptionSubmit={(value) => {
                    setActiveTab(value);
                    closeSearch();
                  }}
                />
              </Popover.Dropdown>
            </Popover>
            <Tabs.List flex={1} miw={0}>
              <Scroller>
                {Object.entries(entityCounts ?? {}).map(
                  ([entityName, count]) => (
                    <Tabs.Tab key={entityName} value={entityName}>
                      {entityName} ({count})
                    </Tabs.Tab>
                  ),
                )}
              </Scroller>
            </Tabs.List>
          </Group>
          {entityNames.map((entityName) => (
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
