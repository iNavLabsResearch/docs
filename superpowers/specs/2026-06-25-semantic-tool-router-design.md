# Local Semantic Tool Router — Design

Date: 2026-06-25

## Problem

Tool discovery/selection for Composio toolkits currently relies on Composio's
hosted **Tool Router** (`composio.tool_router.enabled`), which creates a hosted
MCP session at call setup and proxies tool calls over MCP streamable-http. This
adds network round-trips (session creation at call start, MCP transport per
call). We want a **local** tool selection layer using aurelio-labs
[`semantic-router`](https://docs.aurelio.ai/semantic-router/get-started/introduction)
while **execution stays on Composio** (the official SDK), and a config toggle to
switch between the two.

## Scope

- Semantic router does **selection only** — it maps the latest user utterance to
  the most relevant Composio tool(s). It does **not** execute tools.
- Execution is done by Composio itself via the existing `ComposioToolExecutor`
  (SDK `composio.tools.execute`), not via hosted MCP.
- Priority: **lowest possible latency**. Local in-process encoder, no network in
  the routing hot path.

## Components

### `app/services/semantic_router/` (new package)

- `encoder_factory.py` — lazy process-singleton returning a local
  `FastEmbedEncoder` (`BAAI/bge-small-en-v1.5`, ONNX, no torch). Model loads once
  per process; warmed at startup.
- `semantic_tool_router.py` — `SemanticToolRouter`:
  - `build_from_tool_schemas(schemas: list[dict])` — builds one `Route` per
    Composio function tool; `utterances = [function.name, function.description]`.
  - `select(utterance: str, top_k: int, threshold: float) -> list[str]` — returns
    ordered relevant tool names by router similarity score.
  - Holds the built index so per-turn `select()` is embed-one-utterance + compare
    against cached route embeddings (single-digit ms).
- `__init__.py` — exports.

### Config (`config.json`)

```json
"semantic_router": {
  "enabled": false,
  "model_name": "BAAI/bge-small-en-v1.5",
  "score_threshold": 0.3,
  "top_k": 5
}
```

Mutually exclusive with `composio.tool_router.enabled`: when
`semantic_router.enabled` is true, the hosted Composio tool router path is
bypassed. New `StaticMemoryCache.get_semantic_router_enabled()` and
`get_semantic_router_config()`.

### Execution wiring — shared rewire helper

`composio_sdk_rewire.rewire_composio_tools_to_sdk(...)` is a single shared helper
used by **both** tool-assembly paths in `inferencing_handler_factory.create_agent`:
the pre-compiled fast path (primary, from `compiled_tool_schemas`) and the
`build_tool_execution_stack_from_tools_defs` fallback. When
`semantic_router.enabled`, it:
- Re-points Composio tools from `ToolExecutorType.MCP` to `COMPOSIO` (SDK).
- Removes the hosted/per-tool Composio MCP servers so no MCP session is opened
  (and `apply_composio_runtime_mcp_config` is skipped).
- Builds a `SemanticToolRouter` from the Composio tool schemas.

The compiled path copies the cached mapping/config structures before rewiring so
the shared `agent_with_providers` cache is never mutated. The built router is
passed to the `Agent` constructor.

### Per-turn selection — `agent.py`

In the main `generate()` path (where `tools=self.get_tools()` is passed to the
LLM): when a `SemanticToolRouter` is attached, narrow the Composio tools to the
top-K matching the latest user utterance. **Always keep** non-Composio tools
(`terminate_call`, `transfer_call`, HTTP, webhook) regardless of routing.

## Data flow

```
user utterance
  -> SemanticToolRouter.select(utterance)   # local ONNX embed + cosine, ~ms
  -> narrowed Composio tool schemas (+ always-on system/http tools)
  -> LLM picks tool + args
  -> ToolExecutionManager -> ComposioToolExecutor.execute()  # Composio SDK
```

## Latency notes

- Local FastEmbed ONNX encoder, single model instance per process, warmed at
  startup.
- Route index built once per call at setup, not per turn.
- No hosted MCP session creation at call start; no MCP transport per tool call.

## Testing

Unit tests under `tests/`:
- `SemanticToolRouter.build_from_tool_schemas` creates one route per function.
- `select()` returns the expected tool for a representative utterance.
- Config toggle gating (`get_semantic_router_enabled`).
- Stack builder registers `ToolExecutorType.COMPOSIO` for Composio tools when the
  semantic router is enabled (and does not create a hosted session).

## Dependencies

Add `semantic-router[fastembed]` to `requirements.txt`. Watch the existing
pydantic 2.11.x pin (see requirements.txt note on fastmcp) for conflicts.
