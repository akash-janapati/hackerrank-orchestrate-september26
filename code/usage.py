"""Model-call accounting. Only the final full run writes evaluation/usage_report.md."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CallRecord:
    model: str
    input_tokens: int
    output_tokens: int
    cost: float


@dataclass
class Usage:
    calls: list[CallRecord] = field(default_factory=list)

    def record(self, model: str, input_tokens: int, output_tokens: int, cost: float = 0.0) -> None:
        self.calls.append(CallRecord(model, input_tokens, output_tokens, cost))

    @property
    def total_calls(self) -> int:
        return len(self.calls)

    def summary(self) -> dict:
        total_in = sum(c.input_tokens for c in self.calls)
        total_out = sum(c.output_tokens for c in self.calls)
        total_cost = sum(c.cost for c in self.calls)
        by_model: dict[str, dict] = {}
        for call in self.calls:
            bucket = by_model.setdefault(call.model, {"calls": 0, "in": 0, "out": 0, "cost": 0.0})
            bucket["calls"] += 1
            bucket["in"] += call.input_tokens
            bucket["out"] += call.output_tokens
            bucket["cost"] += call.cost
        return {
            "calls": self.total_calls,
            "input_tokens": total_in,
            "output_tokens": total_out,
            "total_tokens": total_in + total_out,
            "cost": total_cost,
            "by_model": by_model,
        }


USAGE = Usage()


def write_report(path: str, requests: int, provider: str, model: str) -> None:
    summary = USAGE.summary()
    n = max(1, requests)
    lines = [
        "# Token Usage and Cost Analysis",
        "",
        f"- Provider: {provider}",
        f"- Models: {', '.join(summary['by_model']) or model}",
        f"- Model calls: {summary['calls']}",
        f"- Input tokens: {summary['input_tokens']:,}",
        f"- Output tokens: {summary['output_tokens']:,}",
        f"- Total tokens: {summary['total_tokens']:,}",
        f"- Total estimated cost: ${summary['cost']:.6f}",
        f"- Requests: {requests}",
        f"- Average tokens per request: {summary['total_tokens'] / n:,.1f}",
        f"- Average cost per request: ${summary['cost'] / n:.6f}",
        "",
        "## Per model",
        "",
        "| model | calls | input | output | cost |",
        "|---|---|---|---|---|",
    ]
    for name, bucket in summary["by_model"].items():
        lines.append(
            f"| {name} | {bucket['calls']} | {bucket['in']:,} | "
            f"{bucket['out']:,} | ${bucket['cost']:.6f} |"
        )
    lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
