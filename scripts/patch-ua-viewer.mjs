#!/usr/bin/env node

import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join, resolve } from "node:path";

const checkout = resolve(process.argv[2] ?? "");
const dashboard = join(checkout, "understand-anything-plugin/packages/dashboard/src");
if (!existsSync(join(dashboard, "App.tsx"))) {
  throw new Error("Expected pinned Understand Anything dashboard source checkout");
}

const viteConfigPath = join(checkout, "understand-anything-plugin/packages/dashboard/vite.config.ts");
const viteConfig = readFileSync(viteConfigPath, "utf8");
const viteAnchor = "const config: DashboardViteConfig = {\n";
if (!viteConfig.includes(viteAnchor)) throw new Error("Pinned UA Vite config patch anchor missing");
writeFileSync(
  viteConfigPath,
  viteConfig.replace(viteAnchor, `${viteAnchor}  base: "/ua-viewer/",\n`),
);

function replace(file, before, after) {
  const path = join(dashboard, file);
  const source = readFileSync(path, "utf8");
  if (!source.includes(before)) throw new Error(`Pinned UA patch anchor missing in ${file}`);
  writeFileSync(path, source.replace(before, after));
}

replace(
  "App.tsx",
  'import { ThemePicker } from "./components/ThemePicker.tsx";',
  'import { ThemePicker } from "./components/ThemePicker.tsx";\nimport CoIntentBridge from "./components/CoIntentBridge.tsx";',
);
replace(
  "App.tsx",
  'const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";',
  'const DEMO_MODE = import.meta.env.VITE_DEMO_MODE === "true";\nconst COINTENT_EMBEDDED = true;',
);
replace(
  "App.tsx",
  'function dataUrl(fileName: string, token: string | null): string {\n  if (DEMO_MODE) {',
  'function dataUrl(fileName: string, token: string | null): string {\n  if (COINTENT_EMBEDDED && token) {\n    return `/internal/ua-viewer-data/${encodeURIComponent(token)}/${fileName}`;\n  }\n  if (DEMO_MODE) {',
);
replace(
  "App.tsx",
  '  const urlToken = params.get("token");',
  '  const urlToken = params.get(COINTENT_EMBEDDED ? "session" : "token");',
);
replace(
  "App.tsx",
  '    params.delete("token");',
  '    params.delete(COINTENT_EMBEDDED ? "session" : "token");',
);
replace(
  "App.tsx",
  '  const [showOnboarding, setShowOnboarding] = useState(shouldShowOnboarding);',
  '  const [showOnboarding, setShowOnboarding] = useState(COINTENT_EMBEDDED ? false : shouldShowOnboarding);',
);
replace(
  "App.tsx",
  '    <div className="h-screen w-screen flex flex-col bg-root text-text-primary noise-overlay">\n      {/* Header */}',
  '    <div className="h-screen w-screen flex flex-col bg-root text-text-primary noise-overlay">\n      <CoIntentBridge />\n      {/* Header */}',
);
replace(
  "App.tsx",
  '      {allIssues.length > 0 && !loadError && (\n        <WarningBanner issues={allIssues} />\n      )}',
  '      {!COINTENT_EMBEDDED && allIssues.length > 0 && !loadError && (\n        <WarningBanner issues={allIssues} />\n      )}',
);
replace(
  "components/CodeViewer.tsx",
  'function fileContentUrl(filePath: string, token: string): string {\n  const params = new URLSearchParams({ token, path: filePath });\n  return `/file-content.json?${params.toString()}`;\n}',
  'function fileContentUrl(filePath: string, token: string): string {\n  const params = new URLSearchParams({ path: filePath });\n  return `/internal/ua-viewer-data/${encodeURIComponent(token)}/file-content.json?${params.toString()}`;\n}',
);

writeFileSync(join(dashboard, "components/CoIntentBridge.tsx"), `import { useEffect, useRef } from "react";
import { useDashboardStore } from "../store";

const PROTOCOL_VERSION = 1;

type HostMessage = {
  type: "cointent.ua.focus-node" | "cointent.ua.focus-nodes" | "cointent.ua.clear-focus";
  protocolVersion: number;
  requestId: string;
  uaSnapshotId: string;
  nodeId?: string;
  primaryNodeId?: string;
  nodeIds?: string[];
  lineRange?: [number, number];
  openSource?: boolean;
};

function snapshotId(): string {
  return new URLSearchParams(window.location.search).get("ua_snapshot") ?? "";
}

export default function CoIntentBridge() {
  const graph = useDashboardStore((state) => state.graph);
  const selectedNodeId = useDashboardStore((state) => state.selectedNodeId);
  const readySent = useRef(false);

  useEffect(() => {
    if (!graph || readySent.current) return;
    readySent.current = true;
    window.parent.postMessage({
      type: "ua.cointent.ready",
      protocolVersion: PROTOCOL_VERSION,
      requestId: crypto.randomUUID(),
      uaSnapshotId: snapshotId(),
    }, window.location.origin);
  }, [graph]);

  useEffect(() => {
    if (!selectedNodeId || !graph) return;
    window.parent.postMessage({
      type: "ua.cointent.node-selected",
      protocolVersion: PROTOCOL_VERSION,
      requestId: crypto.randomUUID(),
      uaSnapshotId: snapshotId(),
      nodeId: selectedNodeId,
    }, window.location.origin);
  }, [selectedNodeId, graph]);

  useEffect(() => {
    const receive = (event: MessageEvent<HostMessage>) => {
      if (event.origin !== window.location.origin || event.source !== window.parent) return;
      const message = event.data;
      if (!message || message.protocolVersion !== PROTOCOL_VERSION || message.uaSnapshotId !== snapshotId()) return;
      const state = useDashboardStore.getState();
      if (message.type === "cointent.ua.clear-focus") {
        useDashboardStore.setState({ tourHighlightedNodeIds: [] });
        sessionStorage.removeItem("cointent.ua.line-range");
        state.selectNode(null);
        return;
      }
      const candidates = message.type === "cointent.ua.focus-nodes"
        ? [message.primaryNodeId, ...(message.nodeIds ?? [])]
        : [message.nodeId];
      const requested = candidates.find((value): value is string => Boolean(value));
      const focused = candidates.find((value): value is string => Boolean(value && state.nodesById.has(value)));
      if (focused) {
        const highlighted = Array.from(new Set(candidates.filter(
          (value): value is string => Boolean(value && state.nodesById.has(value)),
        )));
        useDashboardStore.setState({ tourHighlightedNodeIds: highlighted });
        state.resetFilters();
        state.setViewMode("structural");
        state.navigateToNode(focused);
        if (message.openSource && state.nodesById.get(focused)?.filePath) {
          if (message.lineRange) sessionStorage.setItem("cointent.ua.line-range", JSON.stringify({ nodeId: focused, lineRange: message.lineRange }));
          else sessionStorage.removeItem("cointent.ua.line-range");
          state.openCodeViewer(focused);
        }
      }
      window.parent.postMessage({
        type: "ua.cointent.focus-result",
        protocolVersion: PROTOCOL_VERSION,
        requestId: message.requestId,
        uaSnapshotId: snapshotId(),
        requestedNodeId: requested ?? "",
        focusedNodeId: focused,
        status: focused ? (focused === requested ? "focused" : "fallback") : "not_found",
      }, window.location.origin);
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, []);

  return null;
}
`);

replace(
  "components/CodeViewer.tsx",
  '  const highlightedRange = useMemo(() => {\n    if (!node?.lineRange) return null;\n    return { start: node.lineRange[0], end: node.lineRange[1] };\n  }, [node?.lineRange]);',
  '  const highlightedRange = useMemo(() => {\n    const rawOverride = sessionStorage.getItem("cointent.ua.line-range");\n    if (rawOverride) {\n      try {\n        const override = JSON.parse(rawOverride) as { nodeId?: string; lineRange?: [number, number] };\n        if (override.nodeId === codeViewerNodeId && Array.isArray(override.lineRange)) {\n          return { start: override.lineRange[0], end: override.lineRange[1] };\n        }\n      } catch {\n        sessionStorage.removeItem("cointent.ua.line-range");\n      }\n    }\n    if (!node?.lineRange) return null;\n    return { start: node.lineRange[0], end: node.lineRange[1] };\n  }, [codeViewerNodeId, node?.lineRange]);',
);

const packagePath = join(checkout, "understand-anything-plugin/packages/dashboard/package.json");
const packageJson = JSON.parse(readFileSync(packagePath, "utf8"));
packageJson.cointentIntegration = {
  protocolVersion: 1,
  upstreamCommit: "5feed1f2ce4f9c368d860f4c0ebc36d98a4693fc",
};
writeFileSync(packagePath, `${JSON.stringify(packageJson, null, 2)}\n`);
