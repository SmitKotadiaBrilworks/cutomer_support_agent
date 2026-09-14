"""Evaluation harness for the customer support agent.

Runs a fixed dataset of conversation turns through the graph and scores:
  1. Intent-classification accuracy (structured-output node)
  2. Tool-selection accuracy (did the agent call the tool we'd expect?)
  3. Escalation correctness (did it escalate exactly when it should?)
  4. (optional, --judge) LLM-as-judge quality score 1-5 on each reply

Usage:
    cd backend
    python -m eval.run_eval            # fast, no extra LLM calls
    python -m eval.run_eval --judge     # also scores reply quality via LLM judge
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage  # noqa: E402

from app.graph import get_graph  # noqa: E402
from app.llm_providers import get_llm  # noqa: E402
from app.schemas import JudgeVerdict  # noqa: E402

DATASET_PATH = Path(__file__).parent / "eval_dataset.jsonl"
RESULTS_DIR = Path(__file__).parent / "results"

JUDGE_SYSTEM_PROMPT = """You are grading a customer support AI's reply for quality.
Score 1-5: 5 = fully and correctly addresses the customer's need, 1 = unhelpful
or wrong. Be strict but fair."""


def load_dataset():
    cases = []
    with open(DATASET_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def run_case(graph, case):
    session_id = f"eval-{case['id']}-{uuid4()}"
    config = {"configurable": {"thread_id": session_id}}
    input_state = {"messages": [HumanMessage(content=case["message"])]}
    if case.get("customer_id"):
        input_state["customer_id"] = case["customer_id"]

    result = graph.invoke(input_state, config)
    tools_used = sorted({m.name for m in result["messages"] if isinstance(m, ToolMessage)})
    return {
        "intent": (result.get("intent") or {}).get("intent"),
        "tools_used": tools_used,
        "escalated": result.get("escalated", False),
        "reply": result["messages"][-1].content,
    }


def score_case(case, actual):
    intent_ok = actual["intent"] == case["expected_intent"]
    tool_ok = case["expected_tool"] is None or case["expected_tool"] in actual["tools_used"]
    escalation_ok = "expect_escalated" not in case or actual["escalated"] == case["expect_escalated"]
    return {"intent_ok": intent_ok, "tool_ok": tool_ok, "escalation_ok": escalation_ok}


def judge_reply(case, actual):
    llm = get_llm(structured_schema=JudgeVerdict)
    verdict: JudgeVerdict = llm.invoke(
        [
            SystemMessage(content=JUDGE_SYSTEM_PROMPT),
            HumanMessage(
                content=f"Customer message: {case['message']}\nAgent reply: {actual['reply']}\n\nScore it."
            ),
        ]
    )
    return verdict.model_dump()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--judge", action="store_true", help="also run LLM-as-judge quality scoring")
    args = parser.parse_args()

    graph = get_graph()
    cases = load_dataset()
    report = []

    print(f"Running {len(cases)} eval cases...\n")
    for case in cases:
        actual = run_case(graph, case)
        scores = score_case(case, actual)
        row = {"id": case["id"], "actual": actual, "scores": scores}

        if args.judge:
            row["judge"] = judge_reply(case, actual)

        report.append(row)

        status = "PASS" if all(scores.values()) else "FAIL"
        judge_str = f" | judge={row['judge']['score']}/5" if args.judge else ""
        print(f"[{status}] {case['id']:<22} intent={actual['intent']:<18} tools={actual['tools_used']}{judge_str}")

    n = len(report)
    intent_acc = sum(r["scores"]["intent_ok"] for r in report) / n
    tool_acc = sum(r["scores"]["tool_ok"] for r in report) / n
    escalation_acc = sum(r["scores"]["escalation_ok"] for r in report) / n

    print("\n--- Summary ---")
    print(f"Intent classification accuracy: {intent_acc:.0%}")
    print(f"Tool-selection accuracy:        {tool_acc:.0%}")
    print(f"Escalation correctness:         {escalation_acc:.0%}")
    if args.judge:
        judge_avg = sum(r["judge"]["score"] for r in report) / n
        print(f"Avg LLM-judge reply quality:    {judge_avg:.1f}/5")

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"report_{datetime.now():%Y%m%d_%H%M%S}.json"
    out_path.write_text(json.dumps(report, indent=2))
    print(f"\nFull report written to {out_path}")


if __name__ == "__main__":
    main()
