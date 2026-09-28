from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from barq_support.agent.agent import build_agent, build_llm
from barq_support.settings import get_settings


class SearchInput(BaseModel):
    query: str = Field(...)


def search(query: str):
    return [
        {
            "article_id": "KB001",
            "text": "Test grounded procedure",
            "score": 0.95,
        }
    ]


tool = StructuredTool.from_function(
    search,
    name="searchKB",
    args_schema=SearchInput,
    description="Search the knowledge base for relevant procedures.",
)

def _run_live_smoke():
    """Manual live smoke test: hits the real configured LLM endpoint.

    Not collected as an automated test -- requires real LLM_* credentials.
    Run directly: `uv run python tests/test_agent_runtime.py`.
    """
    settings = get_settings()

    agent = build_agent(
        build_llm(settings),
        [tool],
        3,
    )

    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Search the KB for a procedure to resolve this test incident.",
                }
            ]
        }
    )

    print(result)


if __name__ == "__main__":
    _run_live_smoke()