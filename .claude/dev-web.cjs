// Starts the Next.js dev server for apps/web from the repo root (used by .claude/launch.json).
const path = require("node:path");

process.chdir(path.join(__dirname, "..", "apps", "web"));
process.argv = [process.argv[0], "next", "dev", "--port", "3000"];
require(path.resolve("node_modules/next/dist/bin/next"));
