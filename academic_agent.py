"""Academic sub-agent: handles questions about upcoming deadlines and helps
the athlete think about balancing coursework with training load."""

import os

from google.adk.agents import Agent
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset
from mcp import StdioServerParameters

SERVER_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "mcp_server",
    "server.py",
)

academic_toolset = MCPToolset(
    connection_params=StdioServerParameters(
        command="python",
        args=[SERVER_PATH],
    ),
)

academic_agent = Agent(
    model="gemini-3.1-flash-lite",
    name="academic_agent",
    description=(
        "Handles questions about upcoming assignments, exams, and how to plan "
        "study time around training days."
    ),
    instruction=(
    "You help a busy student-athlete stay on top of coursework. When asked "
    "about deadlines or assignments, you MUST call the 'get_upcoming_deadlines' "
    "tool first. After the tool returns results, you MUST always write a "
    "plain-text response summarizing what it found -- never end your turn "
    "with just the tool call and no summary. List each deadline with its "
    "course, title, and days until due. If asked to help plan a week, "
    "suggest which days look lighter for studying based on deadline "
    "proximity, and flag anything urgent (due within 2 days) clearly at "
    "the top of your response."
),
    tools=[academic_toolset],
)
