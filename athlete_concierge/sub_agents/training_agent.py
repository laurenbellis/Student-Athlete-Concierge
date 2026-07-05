"""Training sub-agent: handles anything related to today's workout, weights,
1RM tracking, and recovery/soreness logging. Talks to the athlete-concierge
MCP server."""

import os

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from mcp import StdioServerParameters

SERVER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "mcp_server",
    "server.py",
)

training_toolset = MCPToolset(
    connection_params=StdioServerParameters(
        command="python",
        args=[SERVER_PATH],
    ),
)

training_agent = Agent(
    model="gemini-3.1-flash-lite",
    name="training_agent",
    description=(
        "Handles questions about the athlete's workout program: what to "
        "train today (with weights calculated from their real 1RMs), "
        "updating 1RMs, adjusting weight up or down, and logging soreness "
        "or recovery status."
    ),
    instruction=(
        "You are a strength & conditioning assistant for a college athlete. "
        "You MUST always call a tool to answer -- never guess at numbers.\n\n"
        "- To answer 'what's my workout' questions, call 'get_todays_workout'. "
        "It automatically calculates working weight from the athlete's "
        "stored 1RMs and automatically backs off weight if a relevant "
        "muscle group was logged as very sore in the last 2 days. If a "
        "note explains an adjustment, mention it to the athlete.\n"
        "- If an exercise has no 1RM on file, tell the athlete and ask them "
        "for it, then call 'set_one_rep_max' to save it.\n"
        "- If the athlete reports a new 1RM (tested or estimated) for any "
        "lift, call 'set_one_rep_max'.\n"
        "- If the athlete explicitly asks to go lighter or heavier by some "
        "amount (e.g. 'decrease my squat weight by 15%' or 'let's go up "
        "5% today'), call 'adjust_todays_workout' with that percent change.\n"
        "- If the athlete reports being sore or fatigued in a specific "
        "muscle group, call 'log_soreness' with a 1-5 rating.\n\n"
        "After ANY tool call, always write a clear plain-text summary of "
        "the result -- never end your turn with just the tool call and no "
        "explanation. Be encouraging but concise, like a knowledgeable "
        "training partner, not a generic chatbot."
    ),
    tools=[training_toolset],
)
