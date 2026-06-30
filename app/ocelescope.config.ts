import type { OcelescopeConfig } from "@ocelescope/core";
import management from "@ocelescope/management";
import ocelot from "@ocelescope/ocelot";

export default {
	modules: [management, ocelot],
} satisfies OcelescopeConfig;
