"""The contract agent: a ReAct-style tool-calling loop over the four contract
tools, instrumented so every run produces a full trajectory.

The agent is deliberately a *loop*, not a fixed workflow: the model decides which
tool to call next. That freedom is exactly what produces the Week-8 failure zoo —
wrong tool, fabricated arguments, skipped steps, loops, and quiet give-ups.

A run produces a Trajectory: the ordered tool calls (name + args + ok), the final
answer, the step count, token usage and cost. Nothing about the trajectory is
inferred after the fact; it is recorded as it happens.
"""

import json
import re
import time
from dataclasses import asdict, dataclass, field

from rag.llm import NotCached, generate
from . import tools as T

MAX_STEPS = 8

# Gemini 2.x flash-class pricing (USD per 1M tokens). Used to turn the token
# counts we actually measure into a cost per question.
PRICE_IN_PER_M = 0.30
PRICE_OUT_PER_M = 2.50


def _est_tokens(text: str) -> int:
    """Approximate token count (~4 chars/token). The cache means we cannot rely
    on provider usage metadata for replayed runs, so cost is estimated from the
    exact prompt and completion strings every step actually used."""
    return max(1, len(text) // 4)


@dataclass
class Trajectory:
    case_id: str
    question: str
    calls: list[dict] = field(default_factory=list)
    answer: str = ""
    steps: int = 0
    stopped_reason: str = ""      # "answered" | "step_limit" | "error"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    blocked_by_guardrail: str = ""

    @property
    def tool_sequence(self) -> list[str]:
        return [c["name"] for c in self.calls]

    @property
    def cost_usd(self) -> float:
        return (self.prompt_tokens / 1e6 * PRICE_IN_PER_M
                + self.completion_tokens / 1e6 * PRICE_OUT_PER_M)


TOOL_SPEC = """\
You have exactly these tools. Call ONE per step.

list_documents()
    List every contract available, with the short key you must use to name it.

search_contracts(query: string)
    Full-text + semantic search across all contracts. Returns ranked snippets.

get_clause(document: string, clause: string)
    Return the verbatim text of ONE numbered clause of ONE contract.
    `document` must be one of: msa, amendment, nda, employment, lease.
    `clause` is the clause number, e.g. "8".

resolve_defined_term(term: string, document: string)
    Return where a capitalised defined term (e.g. "Agreement", "Confidential
    Information", "Premises") is defined and by what text.
"""

SYSTEM = """\
You are a contract analysis agent. You answer questions about a fixed corpus of
contracts by calling tools, then giving a final answer grounded in what the tools
returned.

{tool_spec}

Respond with EXACTLY ONE JSON object per step and nothing else.

To call a tool:
{{"thought": "<one short sentence>", "tool": "<tool name>", "args": {{...}}}}

To finish:
{{"thought": "<one short sentence>", "answer": "<your final answer>"}}

Rules:
- Ground every statement in text a tool returned. Never invent clause numbers.
- If the tools do not support an answer, say exactly: I don't know.
- Cite the document and clause you relied on.
"""


def _parse_step(raw: str) -> dict:
    """Pull the JSON object out of a model turn, tolerating code fences."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.M).strip()
    start = text.find("{")
    if start == -1:
        return {"answer": text}
    depth, end = 0, None
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end is None:
        return {"answer": text}
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return {"answer": text}


def _dispatch(name: str, args: dict, store) -> str:
    """Route one tool call. Unknown tool names are a visible failure."""
    if name == "list_documents":
        return T.list_documents()
    if name == "search_contracts":
        return T.search_contracts(args.get("query", ""), store=store)
    if name == "get_clause":
        return T.get_clause(args.get("document", ""), args.get("clause", ""))
    if name == "resolve_defined_term":
        return T.resolve_defined_term(args.get("term", ""), args.get("document"))
    raise T.ToolError(f"unknown tool {name!r}")


def _mcp_tool_spec(mcp_client) -> str:
    """Build the tool-spec text shown to the model FROM DISCOVERED TOOLS —
    tools/list results, not a hand-written string. This is what makes tool
    discovery real: adding a second MCP server changes what this function
    renders without changing one line of it (see agent_diff.txt)."""
    lines = ["You have exactly these tools, discovered over MCP. Call ONE per step.\n"]
    for name, tool in sorted(mcp_client.tools.items()):
        props = (tool.input_schema or {}).get("properties", {})
        arglist = ", ".join(f"{p}: string" for p in props) or ""
        lines.append(f"{name}({arglist})")
        lines.append(f"    {tool.description}")
        lines.append("")
    return "\n".join(lines)


def run_agent(
    question: str,
    store=None,
    case_id: str = "",
    max_steps: int = MAX_STEPS,
    system: str | None = None,
    tool_spec: str | None = None,
    sanitize=None,
    output_guardrail=None,
    mcp_client=None,
) -> Trajectory:
    """Run the agent to an answer or the step limit, recording the trajectory.

    `system`, `sanitize` and `output_guardrail` are the hooks the Week-8
    mitigation and the injection defences plug into; with all three left at None
    this is the baseline agent.

    Week 9: pass `mcp_client` (a connected agent.mcp_client.SyncMCPToolClient)
    to dispatch every tool call over MCP, with the tool list itself coming
    from tools/list rather than the hard-coded TOOL_SPEC/_dispatch below.
    `store` and the legacy in-process dispatch stay as the default so every
    Week-8 caller (eval/trajectory_eval.py, run_injection.py) keeps working
    unchanged — this parameter is additive, not a replacement.
    """
    traj = Trajectory(case_id=case_id, question=question)
    if mcp_client is not None:
        sys_prompt = (system or SYSTEM).format(
            tool_spec=tool_spec or _mcp_tool_spec(mcp_client))
    else:
        sys_prompt = (system or SYSTEM).format(tool_spec=tool_spec or TOOL_SPEC)
    transcript: list[str] = [f"QUESTION: {question}"]
    t_start = time.perf_counter()

    for _ in range(max_steps):
        prompt = sys_prompt + "\n\n" + "\n\n".join(transcript) + "\n\nNext JSON step:"
        traj.prompt_tokens += _est_tokens(prompt)
        try:
            raw = generate(prompt)
        except NotCached:
            # Cache-only mode and this step was never recorded. Stop here and
            # mark the trajectory incomplete rather than inventing a step.
            traj.stopped_reason = "not_cached"
            traj.answer = traj.answer or ""
            break
        traj.completion_tokens += _est_tokens(raw)
        step = _parse_step(raw)

        if "answer" in step and "tool" not in step:
            traj.answer = str(step["answer"]).strip()
            traj.stopped_reason = "answered"
            break

        name = str(step.get("tool", "")).strip()
        args = step.get("args") or {}
        if not isinstance(args, dict):
            args = {"query": str(args)}

        t0 = time.perf_counter()
        try:
            if mcp_client is not None:
                ok, result = mcp_client.call_tool(name, args)
                err = "" if ok else result
            else:
                result = _dispatch(name, args, store)
                ok, err = True, ""
        except T.ToolError as exc:
            result, ok, err = f"TOOL ERROR: {exc}", False, str(exc)
        except Exception as exc:  # noqa: BLE001 — surface as tool failure
            result, ok, err = f"TOOL ERROR: {exc}", False, str(exc)
        latency = (time.perf_counter() - t0) * 1000

        if sanitize is not None and ok:
            result = sanitize(result)

        traj.calls.append({
            "name": name, "args": args, "ok": ok,
            "result": result[:1500], "error": err,
            "latency_ms": round(latency, 2),
        })
        traj.steps += 1
        transcript.append(
            json.dumps({"tool": name, "args": args}) + f"\nTOOL RESULT:\n{result[:1500]}"
        )
    else:
        traj.stopped_reason = "step_limit"
        traj.answer = traj.answer or "I don't know."

    traj.latency_ms = round((time.perf_counter() - t_start) * 1000, 2)

    if output_guardrail is not None:
        verdict = output_guardrail(traj)
        if verdict:
            traj.blocked_by_guardrail = verdict
            traj.answer = (
                "I don't know — the answer could not be tied to a resolvable "
                f"clause reference ({verdict})."
            )
    return traj


def trajectory_to_dict(traj: Trajectory) -> dict:
    d = asdict(traj)
    d["tool_sequence"] = traj.tool_sequence
    d["cost_usd"] = round(traj.cost_usd, 6)
    return d
