from typing import List

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from ..servicenow import ServiceNowClient
from ..retrieval.retriever import search_kb


class SearchKBInput(BaseModel):
    query: str = Field(
        ...,
        description="Natural-language query used to search the knowledge base.",
    )


class AddWorkNoteInput(BaseModel):
    note: str = Field(
        ...,
        min_length=1,
        description="Internal processing note to add to the incident.",
    )


class SuggestAnswerInput(BaseModel):
    procedure: str = Field(
        ...,
        min_length=1,
        description="Grounded resolution procedure to suggest.",
    )
    sources: List[str] = Field(
        ...,
        min_length=1,
        description="Knowledge-base sources supporting the procedure.",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0.",
    )


class RequestHRInput(BaseModel):
    reason: str = Field(
        ...,
        min_length=1,
        description="Reason for escalation to human/HR review.",
    )


def build_tools(
    servicenow: ServiceNowClient,
    incident_sys_id: str,
    qdrant_client,
) -> tuple[list[StructuredTool], list[StructuredTool]]:

    retrieved_sources: set[str] = set()
    retrieved_article_ids: set[str] = set()

    def search_kb_tool(query: str) -> list[dict]:
        results = search_kb(
            query=query,
            client=qdrant_client,
        )

        # Demo evidence: show the actual chunks returned by Qdrant.
        print("\n" + "=" * 70)
        print("SEARCHKB RETURNED CHUNKS")
        print("=" * 70)

        for index, result in enumerate(results, start=1):
            print(f"\nChunk {index}")
            print(f"Score:       {result.get('score')}")
            print(f"Article ID:  {result.get('article_id')}")
            print(f"Section:     {result.get('section')}")
            print(f"Chunk Index: {result.get('chunk_index')}")
            print(f"Category:    {result.get('category')}")
            print(f"Text:        {result.get('text', '')}")

        # Track sources returned during this execution.
        for result in results:
            article_id = result.get("article_id")
            chunk_index = result.get("chunk_index")

            if article_id is not None:
                source_id = (
                    f"{article_id}#chunk-{chunk_index}"
                    if chunk_index is not None
                    else str(article_id)
                )

                retrieved_sources.add(source_id)
                retrieved_article_ids.add(str(article_id))

        return results

    def add_work_note_tool(note: str) -> dict:
        return servicenow.add_work_note(
            sys_id=incident_sys_id,
            note=note,
        )

    def suggest_answer_tool(
        procedure: str,
        sources: List[str],
        confidence: float,
    ) -> dict:

        normalized_sources = {
            source.strip()
            for source in sources
        }

        if not all(
            source in retrieved_sources
            or source in retrieved_article_ids
            for source in normalized_sources
        ):
            raise ValueError(
                "suggestAnswer sources must come from "
                "searchKB results retrieved during this execution."
            )

        response = (
            f"{procedure}\n\nSources:\n"
            + "\n".join(f"- {source}" for source in sources)
        )

        return servicenow.suggest_answer(
            sys_id=incident_sys_id,
            response=response,
            confidence=confidence,
        )

    def request_hr_tool(reason: str) -> dict:
        return servicenow.request_hr(
            sys_id=incident_sys_id,
            reason=reason,
        )

    search_tool = StructuredTool.from_function(
        func=search_kb_tool,
        name="searchKB",
        description=(
            "Search the ServiceNow knowledge base using dense vector retrieval. "
            "This tool is repeatable and non-terminal."
        ),
        args_schema=SearchKBInput,
    )

    work_note_tool = StructuredTool.from_function(
        func=add_work_note_tool,
        name="addWorkNote",
        description=(
            "Add an internal processing work note to the current incident. "
            "This tool is repeatable and non-terminal."
        ),
        args_schema=AddWorkNoteInput,
    )

    suggest_tool = StructuredTool.from_function(
        func=suggest_answer_tool,
        name="suggestAnswer",
        description=(
            "Submit a grounded answer suggestion for human review. "
            "This is a terminal tool. Use only when sufficient evidence "
            "has been gathered."
        ),
        args_schema=SuggestAnswerInput,
        return_direct=True,
    )

    hr_tool = StructuredTool.from_function(
        func=request_hr_tool,
        name="requestHR",
        description=(
            "Escalate the incident for human/HR review. "
            "This is a terminal tool."
        ),
        args_schema=RequestHRInput,
        return_direct=True,
    )

    return [search_tool, work_note_tool], [suggest_tool, hr_tool]
