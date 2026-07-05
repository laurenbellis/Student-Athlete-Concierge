"""
Athlete Concierge -- root orchestrator agent.

This is the entry point ADK looks for (`root_agent`). It doesn't do the
domain work itself -- it routes the athlete's request to whichever sub-agent
is best suited: training_agent for anything about workouts/recovery, or
academic_agent for anything about deadlines/coursework.

Run it with:
    adk web      # chat UI at http://localhost:8000
    adk run athlete_concierge   # terminal chat
"""

from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool

from .sub_agents import training_agent, academic_agent

root_agent = Agent(
    model="gemini-3.1-flash-lite",
    name="athlete_concierge",
    description=(
        "A concierge agent for student-athletes that coordinates between "
        "training and academic support."
    ),
    instruction=(
        "You are the front door for a student-athlete's daily assistant. "
        "You must ALWAYS call one of your tools immediately -- never say you "
        "are 'passing along' or 'checking with' a tool without actually "
        "calling it in the same turn. For workout/soreness/recovery questions, "
        "call the training_agent tool right now with the athlete's exact "
        "question. For deadline/study questions, call the academic_agent tool "
        "right now. Do not respond with plain text describing what you're "
        "about to do -- just call the tool."
    ),
    tools=[AgentTool(agent=training_agent), AgentTool(agent=academic_agent)],
)
