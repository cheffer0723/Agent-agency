from agency_swarm import Agent

# Anthropic Claude via LiteLLM. The Agents SDK MultiProvider resolves the
# "litellm/" prefix and LiteLLM reads ANTHROPIC_API_KEY from the environment.
MODEL = "litellm/anthropic/claude-sonnet-4-5-20250929"

beta_support = Agent(
    name="BetaSupport",
    description=(
        "Friendly, honest support specialist for Asymmetry's pre-beta testers. Explains "
        "what Asymmetry is and its pre-beta expectations, sets realistic expectations, "
        "answers grounded questions without inventing product details, and logs bug "
        "reports and feedback for the team."
    ),
    instructions="./instructions.md",
    tools_folder="./tools",
    files_folder="./files",
    model=MODEL,
)
