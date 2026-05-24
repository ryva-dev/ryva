from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime, timezone
from ryva.utils import console
from rich.table import Table
from rich.panel import Panel


# Pricing per 1M tokens (input/output) as of 2026
PROVIDER_PRICING = {
    "anthropic": {
        "claude-sonnet-4-5": {"input": 3.00, "output": 15.00},
        "claude-haiku-4-5": {"input": 0.80, "output": 4.00},
        "claude-opus-4-5": {"input": 15.00, "output": 75.00},
        "default": {"input": 3.00, "output": 15.00},
    },
    "openai": {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "default": {"input": 2.50, "output": 10.00},
    },
    "gemini": {
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "default": {"input": 1.25, "output": 5.00},
    },
    "ollama": {
        "default": {"input": 0.00, "output": 0.00},
    }
}


def calculate_cost(
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int
) -> float:
    provider_prices = PROVIDER_PRICING.get(provider, {})
    model_prices = provider_prices.get(model) or provider_prices.get("default", {"input": 0, "output": 0})
    input_cost = (input_tokens / 1_000_000) * model_prices["input"]
    output_cost = (output_tokens / 1_000_000) * model_prices["output"]
    return round(input_cost + output_cost, 6)


def load_runs(root: Path) -> list[dict]:
    runs_dir = root / "logs" / "runs"
    if not runs_dir.exists():
        return []
    runs = []
    for f in runs_dir.glob("*.json"):
        try:
            runs.append(json.loads(f.read_text()))
        except Exception:
            pass
    return runs


def load_pipeline_runs(root: Path) -> list[dict]:
    runs_dir = root / "logs" / "pipeline_runs"
    if not runs_dir.exists():
        return []
    runs = []
    for f in runs_dir.glob("*.json"):
        try:
            runs.append(json.loads(f.read_text()))
        except Exception:
            pass
    return runs


def get_cost_summary(root: Path, month: str | None = None) -> dict:
    runs = load_runs(root)
    now = datetime.now(timezone.utc)
    current_month = month or now.strftime("%Y-%m")

    monthly_runs = [
        r for r in runs
        if r.get("timestamp", "").startswith(current_month)
    ]

    by_agent: dict[str, dict] = {}
    total_cost = 0.0
    total_tokens = 0

    for run in monthly_runs:
        agent = run.get("agent", "unknown")
        cost = run.get("estimated_cost", 0.0) or 0.0
        input_tokens = run.get("input_tokens", 0) or 0
        output_tokens = run.get("output_tokens", 0) or 0
        tokens = input_tokens + output_tokens

        if agent not in by_agent:
            by_agent[agent] = {
                "runs": 0,
                "cost": 0.0,
                "tokens": 0,
                "avg_latency": 0,
                "total_latency": 0
            }

        by_agent[agent]["runs"] += 1
        by_agent[agent]["cost"] += cost
        by_agent[agent]["tokens"] += tokens
        by_agent[agent]["total_latency"] += run.get("elapsed_ms", 0)
        total_cost += cost
        total_tokens += tokens

    for agent in by_agent:
        runs_count = by_agent[agent]["runs"]
        if runs_count > 0:
            by_agent[agent]["avg_latency"] = int(
                by_agent[agent]["total_latency"] / runs_count
            )
        by_agent[agent]["cost"] = round(by_agent[agent]["cost"], 6)

    return {
        "month": current_month,
        "total_runs": len(monthly_runs),
        "total_cost": round(total_cost, 6),
        "total_tokens": total_tokens,
        "by_agent": by_agent,
    }


def check_budget(root: Path, project: dict) -> list[str]:
    warnings = []
    budget = project.get("budget", {})
    if not budget:
        return warnings

    monthly_limit = budget.get("monthly_limit_usd")
    alert_threshold = budget.get("alert_threshold", 0.8)

    if not monthly_limit:
        return warnings

    summary = get_cost_summary(root)
    current_cost = summary["total_cost"]
    usage_pct = current_cost / monthly_limit

    if usage_pct >= 1.0:
        warnings.append(
            f"[bold red]⚠ BUDGET EXCEEDED:[/bold red] "
            f"${current_cost:.4f} / ${monthly_limit:.2f} "
            f"({usage_pct:.0%} of monthly budget)"
        )
    elif usage_pct >= alert_threshold:
        warnings.append(
            f"[bold yellow]⚠ BUDGET ALERT:[/bold yellow] "
            f"${current_cost:.4f} / ${monthly_limit:.2f} "
            f"({usage_pct:.0%} of monthly budget)"
        )

    # Check per-agent budgets
    agent_budgets = budget.get("agents", {})
    for agent_name, agent_limit in agent_budgets.items():
        agent_data = summary["by_agent"].get(agent_name, {})
        agent_cost = agent_data.get("cost", 0.0)
        if agent_cost >= agent_limit:
            warnings.append(
                f"[bold red]⚠ AGENT BUDGET EXCEEDED:[/bold red] "
                f"{agent_name} ${agent_cost:.4f} / ${agent_limit:.2f}"
            )

    return warnings


def show_cost_report(root: Path, month: str | None = None):
    summary = get_cost_summary(root, month)

    console.print(Panel(
        f"[bold cyan]Cost Report — {summary['month']}[/bold cyan]",
        expand=False
    ))

    # Summary stats
    stats_table = Table(show_header=True, header_style="bold")
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("Value", justify="right")
    stats_table.add_row("Total Runs", str(summary["total_runs"]))
    stats_table.add_row("Total Tokens", f"{summary['total_tokens']:,}")
    stats_table.add_row("Total Cost", f"${summary['total_cost']:.6f}")
    console.print(stats_table)
    console.print()

    if not summary["by_agent"]:
        console.print("[dim]No runs found for this period.[/dim]")
        return

    # Per agent breakdown
    agent_table = Table(
        title="Cost by Agent",
        show_header=True,
        header_style="bold"
    )
    agent_table.add_column("Agent", style="cyan")
    agent_table.add_column("Runs", justify="right")
    agent_table.add_column("Tokens", justify="right")
    agent_table.add_column("Cost", justify="right")
    agent_table.add_column("Avg Latency", justify="right")

    for agent, data in sorted(
        summary["by_agent"].items(),
        key=lambda x: x[1]["cost"],
        reverse=True
    ):
        agent_table.add_row(
            agent,
            str(data["runs"]),
            f"{data['tokens']:,}",
            f"${data['cost']:.6f}",
            f"{data['avg_latency']}ms"
        )

    console.print(agent_table)

    # Check budget
    try:
        from ryva.utils import load_yaml, find_project_root
        project_yml = find_project_root(root) / "project.yml"
        project = load_yaml(project_yml)
        warnings = check_budget(root, project)
        if warnings:
            console.print()
            for w in warnings:
                console.print(w)
    except Exception:
        pass

def get_cost_forecast(root: Path) -> dict:
    """Project monthly spend based on current burn rate."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    days_elapsed = max(now.day, 1)
    days_in_month = 30

    summary = get_cost_summary(root)
    total_cost = summary["total_cost"]
    total_runs = summary["total_runs"]

    daily_rate = total_cost / days_elapsed
    projected_month = daily_rate * days_in_month
    days_remaining = days_in_month - days_elapsed

    # Load budget from project.yml
    try:
        from ryva.utils import find_project_root, load_yaml
        project_yml = find_project_root(root) / "project.yml"
        project = load_yaml(project_yml)
        budget = project.get("budget", {})
        monthly_limit = budget.get("monthly_limit_usd")
    except Exception:
        monthly_limit = None

    days_until_exceeded = None
    if monthly_limit and daily_rate > 0:
        remaining_budget = monthly_limit - total_cost
        if remaining_budget > 0:
            days_until_exceeded = int(remaining_budget / daily_rate)
        else:
            days_until_exceeded = 0

    forecast = {
        "month": now.strftime("%Y-%m"),
        "days_elapsed": days_elapsed,
        "days_remaining": days_remaining,
        "total_cost_so_far": round(total_cost, 6),
        "daily_burn_rate": round(daily_rate, 6),
        "projected_month_total": round(projected_month, 6),
        "total_runs": total_runs,
        "avg_cost_per_run": round(total_cost / total_runs, 6) if total_runs > 0 else 0,
        "monthly_limit": monthly_limit,
        "days_until_budget_exceeded": days_until_exceeded,
    }

    return forecast


def show_forecast(root: Path):
    forecast = get_cost_forecast(root)

    console.print(Panel(
        f"[bold cyan]Cost Forecast — {forecast['month']}[/bold cyan]",
        expand=False
    ))

    table = Table(show_header=True, header_style="bold")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Days elapsed", str(forecast["days_elapsed"]))
    table.add_row("Days remaining", str(forecast["days_remaining"]))
    table.add_row("Spent so far", f"${forecast['total_cost_so_far']:.6f}")
    table.add_row("Daily burn rate", f"${forecast['daily_burn_rate']:.6f}/day")
    table.add_row("Projected month total", f"${forecast['projected_month_total']:.6f}")
    table.add_row("Avg cost per run", f"${forecast['avg_cost_per_run']:.6f}")

    if forecast["monthly_limit"]:
        table.add_row("Monthly limit", f"${forecast['monthly_limit']:.2f}")
        pct = (forecast["total_cost_so_far"] / forecast["monthly_limit"]) * 100
        table.add_row("Budget used", f"{pct:.1f}%")

        if forecast["days_until_budget_exceeded"] is not None:
            days = forecast["days_until_budget_exceeded"]
            if days == 0:
                table.add_row(
                    "Budget status",
                    "[bold red]EXCEEDED[/bold red]"
                )
            elif days <= 3:
                table.add_row(
                    "Days until exceeded",
                    f"[bold red]{days} days[/bold red]"
                )
            elif days <= 7:
                table.add_row(
                    "Days until exceeded",
                    f"[bold yellow]{days} days[/bold yellow]"
                )
            else:
                table.add_row(
                    "Days until exceeded",
                    f"[green]{days} days[/green]"
                )

    console.print(table)

    # Proactive alerts
    if forecast["monthly_limit"]:
        projected = forecast["projected_month_total"]
        limit = forecast["monthly_limit"]
        if projected > limit:
            overage = projected - limit
            console.print(
                f"\n[bold red]⚠ FORECAST ALERT:[/bold red] "
                f"At current burn rate you will exceed your budget by "
                f"[red]${overage:.4f}[/red] this month."
            )
        elif projected > limit * 0.8:
            console.print(
                f"\n[bold yellow]⚠ FORECAST WARNING:[/bold yellow] "
                f"Projected spend ${projected:.4f} is approaching your "
                f"${limit:.2f} limit."
            )
        else:
            console.print(
                f"\n[green]✓ On track:[/green] "
                f"Projected spend ${projected:.4f} is within your "
                f"${limit:.2f} limit."
            )