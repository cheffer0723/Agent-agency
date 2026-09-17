from agency_swarm import Agent

# Anthropic Claude via LiteLLM. The Agents SDK MultiProvider resolves the
# "litellm/" prefix and LiteLLM reads ANTHROPIC_API_KEY from the environment.
MODEL = "litellm/anthropic/claude-haiku-4-5-20251001"

chief_of_staff = Agent(
    name="ChiefOfStaff",
    description=(
        "A ruthless Chief of Staff / program manager for a multi-project portfolio. "
        "Triages ideas and tasks, decides what is beta-blocking versus later, defines "
        "the smallest shippable beta, and keeps the founder shipping instead of drowning "
        "in scope creep."
    ),
    instructions="./instructions.md",
    tools_folder="./tools",
    files_folder="./files",
    model=MODEL,
)
