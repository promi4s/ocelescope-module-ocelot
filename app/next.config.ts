import type { NextConfig } from "next";

const apiBase = process.env.EXTERNAL_API_BASE_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
	reactStrictMode: true,
	// The published @ocelescope/* packages are self-contained (CSS is exported
	// as `<pkg>/styles.css` and imported in _app.tsx), so they don't need to be
	// transpiled here. Only a couple of third-party ESM-only charting libs and
	// your local, untranspiled workspace modules do.
	transpilePackages: ["@mantine/charts", "recharts", "@ocelescope/ocelot"],
	rewrites: async () => [
		{ source: "/api/external/:path*", destination: `${apiBase}/:path*` },
	],
};

export default nextConfig;
