from agency_swarm import Agent


example_agent = Agent(
    name="ExampleAgent",
    description="A helpful and knowledgeable assistant that provides comprehensive support and guidance across various domains.",
    instructions="./instructions.md",
    tools_folder="./tools",
    files_folder="./files",
    # Route to Anthropic Claude via LiteLLM. The SDK's MultiProvider resolves the
    # "litellm/" prefix and LiteLLM reads ANTHROPIC_API_KEY from the environment.
    model="litellm/anthropic/claude-sonnet-4-5-20250929",
)
