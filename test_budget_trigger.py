"""Budget termination logger verifying all 4 safeguards in ContractAgent.

Requirement 4: Enforce all 4 budgets (MAX_ITERS, MAX_TOKENS, MAX_COST, MAX_SECONDS) and produce clean log output.
"""

from pathlib import Path
from rag.agent import ContractAgent
from rag.store import VectorStore

LOG_PATH = Path(__file__).resolve().parent / "budget_termination.log"


def test_and_log_budgets():
    store = VectorStore()
    log_lines = ["==================================================", "WEEK 7 PRACTICAL - BUDGET TERMINATION DEMO LOG", "==================================================\n"]

    test_q = "Under Amendment No. 1, lookup the defined 'Notice Period' for convenience termination, then lookup the defined 'Cure Period' for material breach in the Amendment schedule, and compare both periods."

    # 1. Test MAX_ITERS Budget Trigger
    agent_iters = ContractAgent(store, max_iters=1, max_tokens=10000, max_cost=1.0, max_seconds=60.0)
    res_iters = agent_iters.run(test_q)
    log_lines.append("--- TEST 1: MAX_ITERS BUDGET TRIGGER ---")
    log_lines.append(f"Configured max_iters = 1")
    log_lines.append(f"Terminated by budget: {res_iters.terminated_by_budget}")
    log_lines.append(f"Budget fired: {res_iters.budget_fired}")
    log_lines.append(f"Final Answer: {res_iters.final_answer}")
    log_lines.append("--------------------------------------------------\n")

    # 2. Test MAX_TOKENS Budget Trigger
    agent_tokens = ContractAgent(store, max_iters=10, max_tokens=100, max_cost=1.0, max_seconds=60.0)
    res_tokens = agent_tokens.run(test_q)
    log_lines.append("--- TEST 2: MAX_TOKENS BUDGET TRIGGER ---")
    log_lines.append(f"Configured max_tokens = 100")
    log_lines.append(f"Terminated by budget: {res_tokens.terminated_by_budget}")
    log_lines.append(f"Budget fired: {res_tokens.budget_fired}")
    log_lines.append(f"Final Answer: {res_tokens.final_answer}")
    log_lines.append("--------------------------------------------------\n")

    # 3. Test MAX_COST Budget Trigger
    agent_cost = ContractAgent(store, max_iters=10, max_tokens=10000, max_cost=0.000001, max_seconds=60.0)
    res_cost = agent_cost.run(test_q)
    log_lines.append("--- TEST 3: MAX_COST BUDGET TRIGGER ---")
    log_lines.append(f"Configured max_cost = $0.000001")
    log_lines.append(f"Terminated by budget: {res_cost.terminated_by_budget}")
    log_lines.append(f"Budget fired: {res_cost.budget_fired}")
    log_lines.append(f"Final Answer: {res_cost.final_answer}")
    log_lines.append("--------------------------------------------------\n")

    # 4. Test MAX_SECONDS Budget Trigger
    agent_seconds = ContractAgent(store, max_iters=10, max_tokens=10000, max_cost=1.0, max_seconds=0.00001)
    import time
    time.sleep(0.001)  # ensure wall-clock elapsed time exceeds max_seconds
    res_seconds = agent_seconds.run(test_q)
    log_lines.append("--- TEST 4: MAX_SECONDS BUDGET TRIGGER ---")
    log_lines.append(f"Configured max_seconds = 0.00001s")
    log_lines.append(f"Terminated by budget: {res_seconds.terminated_by_budget}")
    log_lines.append(f"Budget fired: {res_seconds.budget_fired}")
    log_lines.append(f"Final Answer: {res_seconds.final_answer}")
    log_lines.append("==================================================")

    full_log = "\n".join(log_lines)
    LOG_PATH.write_text(full_log, encoding="utf-8")
    print(full_log)


if __name__ == "__main__":
    test_and_log_budgets()
