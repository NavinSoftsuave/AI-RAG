"""Hand-built ReAct Agent for legal contract analysis (~80 lines core loop).

Enforces all 4 budgets:
1. MAX_ITERS (iteration budget)
2. MAX_TOKENS (cumulative tokens summed across all per-lap turns)
3. MAX_COST (dollar cost budget computed from cumulative tokens)
4. MAX_SECONDS (wall-clock timeout)
"""

import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from rag.llm import QuotaExceeded, generate
from rag.store import VectorStore
from rag.tools import (
    ClauseType,
    ContractVersion,
    get_clause,
    get_definitions,
    search_contract,
)

# Cost estimations for Gemini 3.6 Flash
# Input: $0.15 / 1M tokens ($0.00000015 / token)
# Output: $0.60 / 1M tokens ($0.00000060 / token)
PRICE_PER_INPUT_TOKEN = 0.00000015
PRICE_PER_OUTPUT_TOKEN = 0.00000060


@dataclass
class AgentStep:
    lap: int
    thought: str
    tool_name: str
    tool_input: Dict[str, Any]
    tool_output: str
    prompt_tokens: int
    completion_tokens: int
    lap_tokens: int
    lap_cost: float
    elapsed_sec: float


@dataclass
class AgentRunResult:
    question: str
    final_answer: str
    steps: List[AgentStep]
    total_laps: int
    cumulative_tokens: int  # SUM of all laps!
    total_cost: float
    total_latency_sec: float
    terminated_by_budget: bool
    budget_fired: Optional[str]  # "MAX_ITERS", "MAX_TOKENS", "MAX_COST", "MAX_SECONDS"
    success: bool


class ContractAgent:
    def __init__(
        self,
        vector_store: VectorStore,
        max_iters: int = 5,
        max_tokens: int = 8000,
        max_cost: float = 0.01,
        max_seconds: float = 60.0,
    ):
        self.vector_store = vector_store
        self.max_iters = max_iters
        self.max_tokens = max_tokens
        self.max_cost = max_cost
        self.max_seconds = max_seconds

    def _estimate_tokens(self, text: str) -> int:
        """Rough token estimate: 1 token ~= 4 chars."""
        return max(1, len(text) // 4)

    def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Execute a tool and return string output."""
        try:
            if tool_name == "search_contract":
                query = str(tool_args.get("query", ""))
                hits = search_contract(query, self.vector_store, top_k=3)
                if not hits:
                    return "No matching contract chunks found."
                res = []
                for idx, h in enumerate(hits, 1):
                    res.append(f"[{idx}] Source: {h['source']} (chunk {h['chunk_index']})\nText: {h['text']}")
                return "\n\n".join(res)

            elif tool_name == "get_clause":
                raw_type = str(tool_args.get("clause_type", "")).upper()
                try:
                    c_enum = ClauseType(raw_type)
                except ValueError:
                    c_enum = ClauseType.TERMINATION
                hits = get_clause(c_enum, self.vector_store)
                if not hits:
                    return f"No clause content found for type: {c_enum.value}"
                res = []
                for idx, h in enumerate(hits, 1):
                    res.append(f"[{idx}] Clause ({h['source']}): {h['text']}")
                return "\n\n".join(res)

            elif tool_name == "get_definitions":
                term = str(tool_args.get("term_name", ""))
                raw_ver = str(tool_args.get("version", "")).upper()
                try:
                    v_enum = ContractVersion(raw_ver)
                except ValueError:
                    v_enum = ContractVersion.ORIGINAL
                res_dict = get_definitions(term, v_enum)
                return json.dumps(res_dict)

            elif tool_name == "finish":
                return str(tool_args.get("answer", "Task complete."))

            else:
                return f"Error: Unknown tool '{tool_name}'."
        except Exception as exc:
            return f"Error executing tool {tool_name}: {exc}"

    def run(self, question: str) -> AgentRunResult:
        start_time = time.time()
        steps: List[AgentStep] = []
        conversation_history: List[str] = []

        cumulative_tokens = 0
        cumulative_cost = 0.0
        step_count = 0
        final_answer = ""
        terminated_by_budget = False
        budget_fired = None
        success = False

        system_instruction = """
You are an expert contract analysis agent working in a step-by-step loop.
Available tools:
1. `search_contract(query: str)`: Search contract vector store for relevant chunks.
2. `get_clause(clause_type: "TERMINATION"|"NOTICE_PERIOD"|"LIABILITY"|"PAYMENT_TERMS"|"CONFIDENTIALITY"|"GOVERNING_LAW")`: Extract specific clause text.
3. `get_definitions(term_name: str, version: "ORIGINAL"|"AMENDMENT_V1"|"AMENDMENT_V2")`: Lookup defined terms from contract schedules/amendments.
4. `finish(answer: str)`: Final answer when task is complete.

OUTPUT FORMAT (JSON ONLY):
{
  "thought": "Your step-by-step reasoning explaining why you need this action",
  "tool_name": "search_contract" | "get_clause" | "get_definitions" | "finish",
  "tool_input": { ... }
}
"""

        while True:
            step_count += 1
            now = time.time()
            elapsed = now - start_time

            # BUDGET CHECK 1: MAX_SECONDS
            if elapsed >= self.max_seconds:
                terminated_by_budget = True
                budget_fired = "MAX_SECONDS"
                final_answer = f"[BUDGET EXCEEDED] Terminated due to wall-clock timeout ({elapsed:.2f}s >= {self.max_seconds}s)."
                break

            # BUDGET CHECK 2: MAX_ITERS
            if step_count > self.max_iters:
                terminated_by_budget = True
                budget_fired = "MAX_ITERS"
                final_answer = f"[BUDGET EXCEEDED] Terminated due to max iterations ({step_count - 1} >= {self.max_iters})."
                break

            # BUDGET CHECK 3: MAX_TOKENS
            if cumulative_tokens >= self.max_tokens:
                terminated_by_budget = True
                budget_fired = "MAX_TOKENS"
                final_answer = f"[BUDGET EXCEEDED] Terminated due to token budget ({cumulative_tokens} >= {self.max_tokens})."
                break

            # BUDGET CHECK 4: MAX_COST
            if cumulative_cost >= self.max_cost:
                terminated_by_budget = True
                budget_fired = "MAX_COST"
                final_answer = f"[BUDGET EXCEEDED] Terminated due to cost budget (${cumulative_cost:.4f} >= ${self.max_cost:.4f})."
                break

            # Construct Prompt for current lap (incorporating full conversation history)
            prompt = f"{system_instruction}\n\nUSER QUESTION: {question}\n\n"
            if conversation_history:
                prompt += "PREVIOUS STEPS & OBSERVATIONS:\n" + "\n".join(conversation_history) + "\n\n"
            prompt += f"LAP {step_count}: Choose next action (JSON ONLY)."

            prompt_toks = self._estimate_tokens(prompt)

            try:
                raw_response = generate(prompt)
            except Exception as exc:
                final_answer = f"Error during generation: {exc}"
                break

            completion_toks = self._estimate_tokens(raw_response)
            lap_toks = prompt_toks + completion_toks
            lap_cost = (prompt_toks * PRICE_PER_INPUT_TOKEN) + (completion_toks * PRICE_PER_OUTPUT_TOKEN)

            # Accumulate totals across all laps!
            cumulative_tokens += lap_toks
            cumulative_cost += lap_cost

            # Parse JSON decision
            thought = ""
            tool_name = ""
            tool_input = {}
            try:
                # Clean code blocks if present
                clean_json = raw_response.strip()
                if clean_json.startswith("```json"):
                    clean_json = clean_json[7:]
                if clean_json.startswith("```"):
                    clean_json = clean_json[3:]
                if clean_json.endswith("```"):
                    clean_json = clean_json[:-3]
                clean_json = clean_json.strip()

                parsed = json.loads(clean_json)
                thought = parsed.get("thought", "")
                tool_name = parsed.get("tool_name", "")
                tool_input = parsed.get("tool_input", {})
            except Exception:
                # Fallback heuristic if not valid JSON
                thought = "Reasoning from raw model response"
                if "finish" in raw_response.lower():
                    tool_name = "finish"
                    tool_input = {"answer": raw_response}
                else:
                    tool_name = "search_contract"
                    tool_input = {"query": question}

            if tool_name == "finish":
                final_answer = str(tool_input.get("answer", raw_response))
                success = True
                steps.append(
                    AgentStep(
                        lap=step_count,
                        thought=thought,
                        tool_name="finish",
                        tool_input=tool_input,
                        tool_output="Finish execution.",
                        prompt_tokens=prompt_toks,
                        completion_tokens=completion_toks,
                        lap_tokens=lap_toks,
                        lap_cost=lap_cost,
                        elapsed_sec=time.time() - start_time,
                    )
                )
                break

            # Execute tool
            tool_output = self._execute_tool(tool_name, tool_input)

            steps.append(
                AgentStep(
                    lap=step_count,
                    thought=thought,
                    tool_name=tool_name,
                    tool_input=tool_input,
                    tool_output=tool_output,
                    prompt_tokens=prompt_toks,
                    completion_tokens=completion_toks,
                    lap_tokens=lap_toks,
                    lap_cost=lap_cost,
                    elapsed_sec=time.time() - start_time,
                )
            )

            # Record in history for next lap
            conversation_history.append(
                f"Lap {step_count}:\nThought: {thought}\nAction: {tool_name}({tool_input})\nResult: {tool_output}\n"
            )

        total_latency = time.time() - start_time

        return AgentRunResult(
            question=question,
            final_answer=final_answer,
            steps=steps,
            total_laps=len(steps),
            cumulative_tokens=cumulative_tokens,
            total_cost=cumulative_cost,
            total_latency_sec=total_latency,
            terminated_by_budget=terminated_by_budget,
            budget_fired=budget_fired,
            success=success and not terminated_by_budget,
        )
