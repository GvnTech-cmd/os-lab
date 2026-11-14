import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import vm from "node:vm";
import ts from "typescript";
const source = readFileSync(new URL("../src/views/source/brain-model.ts", import.meta.url), "utf8");
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
const sandbox = { exports: {} }; vm.runInNewContext(code, sandbox);
const { brainPath, normalizeGraph, graphWindow } = sandbox.exports;
test("Brain provider paths cannot become external fetches or escape private JSON roots", () => {
  assert.equal(brainPath("graphs/owned.json"), "brain/files/graphs/owned.json");
  for (const path of ["https://example.test/graph.json", "../secret.json", "x/../../control.json", ".private.json", "graph.js"]) assert.throws(() => brainPath(path));
});
test("Brain graph rejects duplicates, caps data and exposes omitted dangling edges", () => {
  const node = { id: "owned", type: "service", label: "Owned", data: {} };
  assert.throws(() => normalizeGraph({ nodes: [node, node], edges: [] }));
  assert.throws(() => normalizeGraph({ nodes: Array(20001).fill(node), edges: [] }));
  const graph = normalizeGraph({ nodes: [node], edges: [{ source: "owned", target: "absent" }] });
  assert.equal(graph.omittedEdges, 1);
});
test("Brain virtual window bounds drawing and respects type and text filters", () => {
  const graph = normalizeGraph({ nodes: Array.from({ length: 300 }, (_, i) => ({ id: String(i), label: `Owned ${i}`, type: i % 2 ? "service" : "job" })), edges: [] });
  assert.equal(graphWindow(graph, "", [], 0).nodes.length, 100);
  assert.equal(graphWindow(graph, "", ["job"], 100).nodes.length, 50);
  assert.equal(graphWindow(graph, "Owned 299", [], 0).nodes[0].id, "299");
});

test("Brain diff preserves unchanged context and bounds long histories", () => {
  const result = sandbox.exports.compareLines("before\ncommon", "after\ncommon");
  assert.equal(result.rows.filter(row => row.kind === "equal")[0].before, "common");
  assert.equal(result.rows.find(row => row.kind === "remove").before, "before");
  assert.equal(result.rows.find(row => row.kind === "add").after, "after");
  assert.equal(sandbox.exports.compareLines(Array(1100).fill("owned").join("\n"), "owned").truncated, true);
});
