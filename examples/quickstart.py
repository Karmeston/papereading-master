from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from finals_agent.agent.runner import run_agent
from finals_agent.core.schemas import AgentRequest, DocumentType, ResearchContext, SearchRequest
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.paper_analysis import PaperStructureAnalyzer
from finals_agent.data.repository import StudyRepository
from finals_agent.data.retrievers import HybridRetriever
from finals_agent.persistence.memory import JsonMemoryStore
from finals_agent.persistence.runs import JsonRunRecorder
from finals_agent.persistence.storage import JsonFileStorage


class FakeAgent:
    def __init__(self):
        self.last_payload = None

    def invoke(self, payload):
        self.last_payload = payload
        user_question = payload["messages"][-1]["content"]
        return {
            "messages": [
                SimpleNamespace(content=user_question),
                SimpleNamespace(content=f"Fake paper-reading answer for: {user_question}"),
            ]
        }


def main() -> None:
    with TemporaryDirectory() as temp_dir:
        workspace = Path(temp_dir)
        source = workspace / "rag_paper.md"
        source.write_text(
            "\n\n".join(
                [
                    "Abstract",
                    "We study retrieval augmented generation for knowledge-intensive tasks.",
                    "1 Introduction",
                    "Figure 1: Retrieval and generation pipeline.",
                    "Table 1: Results on benchmark datasets.",
                    "score = softmax(q k)",
                    "Conclusion",
                    "Retrieval improves factual grounding but adds latency.",
                ]
            ),
            encoding="utf-8",
        )

        repository = StudyRepository(
            index_path=workspace / "index.json",
            raw_data_dir=workspace / "raw",
        )
        retriever = HybridRetriever(repository)
        memory_store = JsonMemoryStore(JsonFileStorage(workspace / "memory.json"))
        run_recorder = JsonRunRecorder(JsonFileStorage(workspace / "runs.json"))
        agent = FakeAgent()

        ingest_result = ingest_material(
            build_ingest_request(
                source_path=source,
                document_type=DocumentType.PAPER,
                field="nlp",
                focus="retrieval augmented generation",
                tags=("example",),
            ),
            repository=repository,
        )

        search_response = retriever.search(
            SearchRequest(
                query="retrieval generation",
                field="nlp",
                focus="retrieval augmented generation",
            )
        )

        structure = PaperStructureAnalyzer(repository).analyze(title="rag_paper")

        run_result = run_agent(
            AgentRequest(
                question="总结这篇论文的创新点，并说明图表和公式的作用",
                course_context=ResearchContext(field="nlp", focus="retrieval augmented generation"),
                conversation_id="quickstart",
            ),
            repository=repository,
            retriever=retriever,
            agent=agent,
            memory_store=memory_store,
            run_recorder=run_recorder,
        )

        print("== ingest ==")
        print(ingest_result.message)
        print(ingest_result.metadata["processing"])

        print("\n== search ==")
        print(search_response.metadata)
        for item in search_response.results:
            print(item.to_dict())

        print("\n== structure ==")
        print(structure.to_dict())

        print("\n== agent run ==")
        print(run_result.answer)
        print("task:", run_result.metadata["task_plan"]["intent"]["task_type"])
        print("preretrieval:", run_result.metadata["preretrieval"])
        print("context blocks:", run_result.metadata["context"]["blocks"])

        print("\n== persisted records ==")
        print("memory messages:", len(memory_store.get("quickstart").messages))
        print("run records:", len(run_recorder.list_records()))


if __name__ == "__main__":
    main()
