// Third-party global styles the @ocelescope modules rely on. Import these
// FIRST and in this order — @mantine/core must come before the others, and
// every @ocelescope/* scoped stylesheet must come AFTER them so its overrides
// win. Each @ocelescope package's README lists the styles it needs.
import "@mantine/core/styles.css";
import "@mantine/dates/styles.css";
import "@mantine/charts/styles.css";
import "@mantine/dropzone/styles.css";
import "@mantine/notifications/styles.css";
import "mantine-datatable/styles.css";
import "@xyflow/react/dist/style.css";

// @ocelescope packages' own (scoped) styles.
import "@ocelescope/core/styles.css";
import "@ocelescope/ocelot/styles.css";

import { OcelescopeApp } from "@ocelescope/core";
import config from "../ocelescope.config";

export default OcelescopeApp(config);
