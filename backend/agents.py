"""Campus Customs multi-agent team (PydanticAI).

Five agents -- boss, inventory, accounting, facilities, customer_service -- share
one connection to the Campus Customs MCP server. Each agent sees only the MCP
tools it needs, and every agent has a `delegate` tool so it can hand work to any
other agent (full connectivity). Boss decides which agents a ticket needs; it is
never forced to call all of them.

Model: gpt-6-luna through Portkey, for every agent. No other model is used.
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastmcp import Client
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit  # noqa: E402

HW5_DIR = Path(__file__).resolve().parent.parent
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
load_dotenv(HW5_DIR / ".env")
load_dotenv(HW5_DIR.parent / ".env")  # repo-root .env holds PORTKEY_API_KEY
os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

# ---------------------------------------------------------------- model (fixed)
MODEL_NAME = "gpt-6-luna"  # the ONLY model allowed in this assignment; intentionally not configurable
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# ---------------------------------------------------------------- token / cost controls
MAX_OUTPUT_TOKENS = 1500           # per model response
MAX_DELEGATION_DEPTH = 2           # boss -> specialist -> specialist, no deeper
MAX_DELEGATIONS_PER_TICKET = 6     # across the whole ticket run
TICKET_USAGE_LIMITS = UsageLimits(  # shared by every agent working on one ticket
    request_limit=30,
    tool_calls_limit=40,
    total_tokens_limit=150_000,
)
MODEL_SETTINGS = ModelSettings(max_tokens=MAX_OUTPUT_TOKENS, parallel_tool_calls=False)

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
AGENT_NAMES: tuple[str, ...] = ("boss", "inventory", "accounting", "facilities", "customer_service")

# Least-privilege MCP tool access per agent (enforced twice: tool list filter + call-time check).
TOOL_ACCESS: dict[str, set[str]] = {
    "boss": {"get_open_tickets", "get_ticket_context", "update_ticket_status"},
    "inventory": {"get_ticket_context", "check_stock_and_restock"},
    "accounting": {"get_ticket_context", "get_cash_position", "check_stock_and_restock", "quote_discount",
                   "request_payment", "request_purchase_order"},
    "facilities": {"get_ticket_context", "get_cash_position", "create_draft"},
    "customer_service": {"get_ticket_context", "create_draft"},
}
# Identity fields are filled in by the harness so an agent can't act under another name.
IDENTITY_ARGS = ("requested_by", "author", "updated_by")


class TicketOutcome(BaseModel):
    """Boss's final decision for one ticket."""
    ticket_id: int
    status: Literal["resolved", "waiting_approval", "blocked", "in_progress"]
    agents_used: list[str] = Field(description="Agents that actually worked on the ticket, including boss")
    decision: str = Field(description="Boss's final decision and the reason, in 2-4 sentences")
    actions: list[str] = Field(description="Concrete things that were done (requests queued, drafts saved, ...)")
    approval_request_ids: list[int] = Field(default_factory=list)
    draft_ids: list[int] = Field(default_factory=list)


@dataclass
class TicketBudget:
    delegations: int = 0


@dataclass
class TeamDeps:
    run_id: str
    ticket_id: int | None
    agent: str
    depth: int = 0
    chain: list[str] = field(default_factory=list)
    budget: TicketBudget = field(default_factory=TicketBudget)


class MissingAPIKey(RuntimeError):
    pass


# ---------------------------------------------------------------- MCP toolset

def _mcp_client() -> Client:
    """Launch the MCP server exactly as configured in HW5/.mcp.json."""
    cfg = json.loads((HW5_DIR / ".mcp.json").read_text())["mcpServers"]["campus-customs"]
    cfg = {**cfg, "command": str(HW5_DIR / cfg["command"]), "args": [str(HW5_DIR / a) for a in cfg["args"]]}
    return Client({"mcpServers": {"campus-customs": cfg}})


async def _audited_tool_call(ctx: RunContext[TeamDeps], call_tool, name: str, args: dict[str, Any]):
    d = ctx.deps
    if name not in TOOL_ACCESS[d.agent]:
        audit.log("tool_denied", run_id=d.run_id, ticket_id=d.ticket_id, agent=d.agent, tool=name, args=args)
        return {"error": f"{d.agent} is not allowed to call {name}; delegate to the right agent instead."}
    args = {**args, **{k: d.agent for k in IDENTITY_ARGS if k in args}}
    result = await call_tool(name, args)
    audit.log("tool_call", run_id=d.run_id, ticket_id=d.ticket_id, agent=d.agent, tool=name,
              args=args, result=result)
    return result


@lru_cache(maxsize=1)
def mcp_toolset() -> MCPToolset:
    return MCPToolset(_mcp_client(), process_tool_call=_audited_tool_call, max_retries=1)


def _agent_tools(ctx: RunContext[TeamDeps], tool_def) -> bool:
    return tool_def.name in TOOL_ACCESS[ctx.deps.agent]


# ---------------------------------------------------------------- agents

def _model() -> OpenAIResponsesModel:
    api_key = os.getenv("PORTKEY_API_KEY")
    if not api_key:
        raise MissingAPIKey("PORTKEY_API_KEY is not set in the environment or .env")
    # Responses API: gpt-6-luna on Portkey only supports function tools there (not on chat/completions).
    return OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(api_key=api_key, base_url=PORTKEY_BASE_URL))


async def delegate(ctx: RunContext[TeamDeps], to: AgentName, task: str) -> str:
    """Hand a focused sub-task to another agent and get its report back.

    Use only when that agent's expertise is actually needed. Write `task` as a
    self-contained instruction: include the ticket id and the facts the other
    agent needs (SKU, size, qty, invoice/lease id, amounts).
    Agents: inventory (stock, shortages, vendors, lead times), accounting (cash,
    invoices, margins, payment / purchase-order requests for human approval),
    facilities (lease, rent, shop space), customer_service (customer drafts),
    boss (final decisions / conflicts).
    """
    d = ctx.deps
    refusal = None
    if to == d.agent:
        refusal = "You cannot delegate to yourself."
    elif d.depth >= MAX_DELEGATION_DEPTH:
        refusal = f"Delegation depth limit ({MAX_DELEGATION_DEPTH}) reached; finish the task with what you have."
    elif d.budget.delegations >= MAX_DELEGATIONS_PER_TICKET:
        refusal = f"Ticket delegation budget ({MAX_DELEGATIONS_PER_TICKET}) used up; finish with what you have."
    if refusal:
        audit.log("delegation_refused", run_id=d.run_id, ticket_id=d.ticket_id, agent=d.agent, to=to, reason=refusal)
        return refusal

    d.budget.delegations += 1
    child = TeamDeps(run_id=d.run_id, ticket_id=d.ticket_id, agent=to, depth=d.depth + 1,
                     chain=[*d.chain, d.agent], budget=d.budget)
    audit.log("delegation", run_id=d.run_id, ticket_id=d.ticket_id, agent=d.agent, to=to, task=task,
              chain=child.chain)
    result = await get_agents()[to].run(task, deps=child, usage=ctx.usage, usage_limits=TICKET_USAGE_LIMITS)
    output = result.output.model_dump() if isinstance(result.output, BaseModel) else result.output
    audit.log("delegation_result", run_id=d.run_id, ticket_id=d.ticket_id, agent=to, reported_to=d.agent,
              output=output)
    return json.dumps(output) if not isinstance(output, str) else output


@lru_cache(maxsize=1)
def get_agents() -> dict[str, Agent]:
    model = _model()
    toolset = mcp_toolset().filtered(_agent_tools)
    agents: dict[str, Agent] = {}
    for name in AGENT_NAMES:
        agent = Agent(
            model,
            name=name,
            deps_type=TeamDeps,
            output_type=TicketOutcome if name == "boss" else str,
            instructions=(PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8"),
            toolsets=[toolset],
            tools=[delegate],
            model_settings=MODEL_SETTINGS,
            retries=2,
        )

        @agent.instructions
        def who_am_i(ctx: RunContext[TeamDeps]) -> str:
            d = ctx.deps
            via = " -> ".join(d.chain) if d.chain else "the dashboard"
            return (f"## Run context\n- You are `{d.agent}`. Ticket: {d.ticket_id}. Task came from {via}.\n"
                    f"- Delegation depth {d.depth}/{MAX_DELEGATION_DEPTH}; ticket delegations used "
                    f"{d.budget.delegations}/{MAX_DELEGATIONS_PER_TICKET}.")

        agents[name] = agent
    return agents


# ---------------------------------------------------------------- entry point

async def run_ticket(ticket_id: int, run_id: str | None = None) -> TicketOutcome:
    """Have Boss work one ticket end to end. All activity goes to output/audit_trail.json."""
    run_id = run_id or uuid.uuid4().hex[:12]
    deps = TeamDeps(run_id=run_id, ticket_id=ticket_id, agent="boss")
    audit.log("ticket_started", run_id=run_id, ticket_id=ticket_id, agent="boss", model=MODEL_NAME)
    try:
        async with mcp_toolset():  # one MCP server process for the whole ticket
            result = await get_agents()["boss"].run(
                f"Work ticket {ticket_id}. Read it with get_ticket_context, involve only the agents it needs, "
                "make the final decision, and record it with update_ticket_status.",
                deps=deps, usage_limits=TICKET_USAGE_LIMITS)
    except Exception as exc:
        audit.log("ticket_failed", run_id=run_id, ticket_id=ticket_id, agent="boss",
                  error=f"{type(exc).__name__}: {exc}", delegations=deps.budget.delegations)
        raise
    usage = result.usage
    audit.log("ticket_finished", run_id=run_id, ticket_id=ticket_id, agent="boss",
              outcome=result.output.model_dump(), delegations=deps.budget.delegations,
              usage={"requests": usage.requests, "tool_calls": usage.tool_calls,
                     "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                     "total_tokens": usage.total_tokens})
    return result.output
