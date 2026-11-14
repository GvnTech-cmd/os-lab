export interface BrainNode { id: string; type: string; label: string; data: Record<string, unknown> }
export interface BrainEdge { id: string; source: string; target: string; label: string; type: string }
export interface BrainGraph { meta: Record<string, unknown>; nodes: BrainNode[]; edges: BrainEdge[]; omittedEdges: number }
export interface BrainTab { id: string; label: string; file: string }
export interface BrainManifest { tabs: BrainTab[]; providers?: Record<string, string>; date?: string }
export function brainPath(file: string): string {
  if (!file.endsWith(".json") || file.length > 1000 || file.split("/").some(part => !/^[A-Za-z0-9_][A-Za-z0-9_.-]*$/.test(part))) throw new Error("Invalid Brain provider path");
  return "brain/files/" + file.split("/").map(encodeURIComponent).join("/");
}
export function normalizeGraph(raw: unknown): BrainGraph {
  if (!raw || typeof raw !== "object") throw new Error("Invalid Brain graph");
  const value = raw as Record<string, unknown>;
  if (!Array.isArray(value.nodes) || !Array.isArray(value.edges) || value.nodes.length > 20000 || value.edges.length > 50000) throw new Error("Invalid or oversized Brain graph");
  const ids = new Set<string>();
  const nodes = value.nodes.map((node: unknown): BrainNode => {
    if (!node || typeof node !== "object") throw new Error("Invalid Brain node");
    const item = node as Record<string, unknown>;
    if (typeof item.id !== "string" || !item.id || item.id.length > 512 || ids.has(item.id)) throw new Error("Invalid or duplicate Brain node");
    ids.add(item.id);
    return { id: item.id, type: String(item.type ?? "unknown"), label: String(item.label ?? item.id), data: item.data && typeof item.data === "object" && !Array.isArray(item.data) ? item.data as Record<string, unknown> : {} };
  });
  const edges: BrainEdge[] = [];
  for (const [index, edge] of value.edges.entries()) {
    if (!edge || typeof edge !== "object") continue;
    const item = edge as Record<string, unknown>;
    if (typeof item.source !== "string" || typeof item.target !== "string" || !ids.has(item.source) || !ids.has(item.target)) continue;
    edges.push({ id: String(item.id ?? index), source: item.source, target: item.target, label: String(item.label ?? ""), type: String(item.type ?? "unknown") });
  }
  return { meta: value.meta && typeof value.meta === "object" ? value.meta as Record<string, unknown> : {}, nodes, edges, omittedEdges: value.edges.length - edges.length };
}
export function graphWindow(graph: BrainGraph, query: string, types: string[], offset: number, size = 100) {
  const nodes = graph.nodes.filter(node => (!types.length || types.includes(node.type)) && `${node.id} ${node.label} ${JSON.stringify(node.data)}`.toLowerCase().includes(query.toLowerCase()));
  const page = nodes.slice(Math.max(0, offset), Math.max(0, offset) + Math.min(200, size));
  const ids = new Set(page.map(node => node.id));
  return { nodes: page, edges: graph.edges.filter(edge => ids.has(edge.source) && ids.has(edge.target)), total: nodes.length };
}

/** Bounded LCS line diff; no source is executed or sent to another service. */
export function compareLines(before: string, after: string, limit = 1000) {
  const a = before.split(/\r?\n/), b = after.split(/\r?\n/);
  const m = Math.min(a.length, limit), n = Math.min(b.length, limit), width = n + 1;
  const table = new Uint16Array((m + 1) * width);
  for (let i = m - 1; i >= 0; i--) for (let j = n - 1; j >= 0; j--) table[i * width + j] = a[i] === b[j] ? 1 + table[(i + 1) * width + j + 1] : Math.max(table[(i + 1) * width + j], table[i * width + j + 1]);
  const rows: { before?: string; after?: string; kind: string }[] = [];
  let i = 0, j = 0;
  while (i < m || j < n) {
    if (i < m && j < n && a[i] === b[j]) { rows.push({ before: a[i++], after: b[j++], kind: "equal" }); }
    else if (i < m && (j === n || table[(i + 1) * width + j] >= table[i * width + j + 1])) rows.push({ before: a[i++], kind: "remove" });
    else rows.push({ after: b[j++], kind: "add" });
  }
  return { rows, truncated: a.length > m || b.length > n };
}
