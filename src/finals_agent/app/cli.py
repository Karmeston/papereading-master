from __future__ import annotations

import argparse
import json
from pathlib import Path

from finals_agent.core.config import ensure_data_dirs, load_settings
from finals_agent.core.exceptions import FinalsAgentError
from finals_agent.core.observability import configure_logging
from finals_agent.core.runtime import AgentRuntime
from finals_agent.core.schemas import DocumentType
from finals_agent.data.repository import StudyRepository


def main() -> None:
    settings = load_settings(validate=False)
    ensure_data_dirs(settings.paths)

    parser = argparse.ArgumentParser(prog="paper-agent")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Upload/register a local .pdf, .txt, or .md paper file.")
    ingest_parser.add_argument("path", type=Path)
    ingest_parser.add_argument("--type", required=True, choices=[item.value for item in DocumentType])
    ingest_parser.add_argument("--field", "--course", dest="field", required=True)
    ingest_parser.add_argument("--title")
    ingest_parser.add_argument("--focus", "--chapter", dest="focus")
    ingest_parser.add_argument("--source")
    ingest_parser.add_argument("--tag", action="append", default=[])

    list_parser = subparsers.add_parser("list", help="List local uploaded papers and notes.")
    list_parser.add_argument("--field", "--course", dest="field")

    remove_parser = subparsers.add_parser("remove", help="Remove a local paper and its sidecar files.")
    remove_parser.add_argument("document_id")

    search_parser = subparsers.add_parser("search", help="Search local uploaded paper text.")
    search_parser.add_argument("query")
    search_parser.add_argument("--field", "--course", dest="field")
    search_parser.add_argument("--type", choices=[item.value for item in DocumentType])

    analyze_parser = subparsers.add_parser("analyze", help="Analyze local paper sections, captions, formulas, and paragraphs.")
    analyze_parser.add_argument("--document-id")
    analyze_parser.add_argument("--title")
    analyze_parser.add_argument("--query")
    analyze_parser.add_argument("--json", action="store_true")

    related_parser = subparsers.add_parser("related", help="Search arXiv for related papers.")
    related_parser.add_argument("topic")
    related_parser.add_argument("--limit", type=int, default=5)
    related_parser.add_argument("--json", action="store_true")

    download_parser = subparsers.add_parser(
        "download",
        help="Download an arXiv PDF and import it into the local library.",
    )
    download_parser.add_argument("url")
    download_parser.add_argument("--title", required=True)
    download_parser.add_argument("--field", default="arXiv")
    download_parser.add_argument("--tag", action="append", default=[])
    download_parser.add_argument("--json", action="store_true")

    read_parser = subparsers.add_parser("read", help="Build an evidence-backed reading workflow for one local paper.")
    read_parser.add_argument("--document-id")
    read_parser.add_argument("--title")
    read_parser.add_argument("--query")
    read_parser.add_argument("--field", "--course", dest="field")
    read_parser.add_argument("--related-limit", type=int, default=0)
    read_parser.add_argument("--json", action="store_true")

    explain_parser = subparsers.add_parser("explain", help="Explain a paper section, paragraph, figure, table, formula, or concept.")
    explain_parser.add_argument("target")
    explain_parser.add_argument("--document-id")
    explain_parser.add_argument("--title")
    explain_parser.add_argument("--query")
    explain_parser.add_argument("--field", "--course", dest="field")
    explain_parser.add_argument("--limit", type=int, default=5)
    explain_parser.add_argument("--json", action="store_true")

    compare_parser = subparsers.add_parser("compare", help="Compare a local paper against related papers for novelty and differences.")
    compare_parser.add_argument("topic")
    compare_parser.add_argument("--document-id")
    compare_parser.add_argument("--title")
    compare_parser.add_argument("--query")
    compare_parser.add_argument("--field", "--course", dest="field")
    compare_parser.add_argument("--related-limit", type=int, default=5)
    compare_parser.add_argument("--json", action="store_true")

    progress_parser = subparsers.add_parser("progress", help="View or update paper reading progress and open reading items.")
    progress_parser.add_argument("--document-id")
    progress_parser.add_argument("--title")
    progress_parser.add_argument("--field", "--course", dest="field")
    progress_parser.add_argument("--status", choices=["not_started", "reading", "reviewing", "done"])
    progress_parser.add_argument("--section")
    progress_parser.add_argument("--percent", type=int)
    progress_parser.add_argument("--summary")
    progress_parser.add_argument("--json", action="store_true")

    note_parser = subparsers.add_parser("note", help="Add a reading note, open question, or verification item for a paper.")
    note_parser.add_argument("text")
    note_parser.add_argument("--kind", choices=["note", "question", "verification"], default="note")
    note_parser.add_argument("--document-id")
    note_parser.add_argument("--title")
    note_parser.add_argument("--field", "--course", dest="field")
    note_parser.add_argument("--section")
    note_parser.add_argument("--page", type=int)
    note_parser.add_argument("--citation")
    note_parser.add_argument("--json", action="store_true")

    flashcard_parser = subparsers.add_parser("flashcard", help="Add a review flashcard for a paper.")
    flashcard_parser.add_argument("--question", required=True)
    flashcard_parser.add_argument("--answer", required=True)
    flashcard_parser.add_argument("--document-id")
    flashcard_parser.add_argument("--title")
    flashcard_parser.add_argument("--field", "--course", dest="field")
    flashcard_parser.add_argument("--section")
    flashcard_parser.add_argument("--page", type=int)
    flashcard_parser.add_argument("--citation")
    flashcard_parser.add_argument("--json", action="store_true")

    mark_parser = subparsers.add_parser("mark", help="Mark a reading note, question, verification item, or flashcard.")
    mark_parser.add_argument("item_id")
    mark_parser.add_argument("--status", required=True, choices=["open", "done", "archived"])
    mark_parser.add_argument("--document-id")
    mark_parser.add_argument("--title")
    mark_parser.add_argument("--field", "--course", dest="field")
    mark_parser.add_argument("--json", action="store_true")

    runs_parser = subparsers.add_parser("runs", help="List recent agent run records.")
    runs_parser.add_argument("--limit", type=int, default=10)
    runs_parser.add_argument("--json", action="store_true")

    ui_parser = subparsers.add_parser("ui", help="Start the local Paper Agent web UI.")
    ui_parser.add_argument("--host", default="127.0.0.1")
    ui_parser.add_argument("--port", type=int, default=8765)
    ui_parser.add_argument("--open", action="store_true")
    ui_parser.add_argument("--app", action="store_true", help="Open the UI in a standalone browser app window.")

    embed_parser = subparsers.add_parser("embed", help="Build or rebuild local embedding indexes for uploaded papers.")
    embed_parser.add_argument("--document-id")
    embed_parser.add_argument("--field", "--course", dest="field")
    embed_parser.add_argument("--force", action="store_true")

    chat_parser = subparsers.add_parser("chat", help="Ask the paper-reading LangChain agent.")
    chat_parser.add_argument("question")
    chat_parser.add_argument("--field", "--course", dest="field")
    chat_parser.add_argument("--document-id")
    chat_parser.add_argument("--title")
    chat_parser.add_argument("--conversation-id")
    chat_parser.add_argument("--debug", action="store_true")
    chat_parser.add_argument("--stream", action="store_true")

    evals_parser = subparsers.add_parser("evals", help="Run eval suites for project protocols and answer quality.")
    evals_parser.add_argument("--suite", choices=["smoke", "grounded", "llm_judge"], default="smoke")
    evals_parser.add_argument("--real-model", action="store_true")
    evals_parser.add_argument("--real-judge", action="store_true")
    evals_parser.add_argument("--debug", action="store_true")

    args = parser.parse_args()
    debug = getattr(args, "debug", False) or settings.runtime.debug
    configure_logging(debug=debug)
    repository = StudyRepository()

    try:
        if args.command == "ingest":
            from finals_agent.data.ingestion import build_ingest_request, ingest_material
            from finals_agent.data.embeddings import build_embedding_provider

            result = ingest_material(
                build_ingest_request(
                    source_path=args.path,
                    document_type=DocumentType(args.type),
                    field=args.field,
                    title=args.title,
                    focus=args.focus,
                    source=args.source,
                    tags=tuple(args.tag),
                ),
                repository=repository,
                embedding_provider=(
                    build_embedding_provider(settings.embeddings)
                    if settings.embeddings.provider != "disabled"
                    else None
                ),
            )
            document = result.document
            print(f"Ingested {document.document_type.value}: {document.field} / {document.title} ({document.id})")
            if result.metadata.get("embedding_index_path"):
                print(f"Embedding index: {result.metadata['embedding_index_path']}")
            return

        if args.command == "list":
            documents = repository.list_documents(field=args.field)
            if not documents:
                print("No local papers found.")
                return
            for document in documents:
                print(f"[{document.document_type.value}] {document.field} / {document.title} ({document.id})")
            return

        if args.command == "remove":
            document = repository.remove_document(args.document_id)
            print(f"Removed {document.document_type.value}: {document.field} / {document.title} ({document.id})")
            return

        if args.command == "search":
            document_type = DocumentType(args.type) if args.type else None
            results = repository.search(args.query, field=args.field, document_type=document_type)
            if not results:
                print("No matching local paper snippet found.")
                return
            for item in results:
                print(f"[{item.document_type.value}] {item.field} / {item.title} ({item.document_id})")
                print(f"  {item.snippet}")
            return

        if args.command == "analyze":
            from finals_agent.data.paper_analysis import PaperStructureAnalyzer

            structure = PaperStructureAnalyzer(repository).analyze(
                document_id=args.document_id,
                title=args.title,
                query=args.query,
            )
            if args.json:
                print(json.dumps(structure.to_dict(), ensure_ascii=False, indent=2))
                return
            print(f"Paper: {structure.title} ({structure.document_id})")
            print(f"Sections: {len(structure.section_headings)}")
            print(f"Paragraphs: {structure.paragraph_count}")
            print(f"Figures: {len(structure.figure_captions)} captions, images={structure.image_count}")
            print(f"Tables: {len(structure.table_captions)} captions")
            print(f"Formula candidates: {len(structure.formula_candidates)}")
            print(f"Structured artifacts: {len(structure.artifacts)}")
            print(f"Artifact interpretations: {len(structure.artifact_interpretations)}")
            for heading in structure.section_headings[:10]:
                print(f"  - {heading}")
            for artifact in structure.artifacts[:5]:
                print(f"  [{artifact.kind}] page={artifact.page} chunk={artifact.chunk_id}: {artifact.text}")
            for interpretation in structure.artifact_interpretations[:3]:
                print(f"  interpretation[{interpretation.kind}] confidence={interpretation.confidence}: {interpretation.interpretation}")
            return

        if args.command == "related":
            from finals_agent.data.external_search import ArxivPaperSearch

            papers = ArxivPaperSearch().search(args.topic, limit=args.limit)
            if args.json:
                print(json.dumps([paper.to_dict() for paper in papers], ensure_ascii=False, indent=2))
                return
            if not papers:
                print("No related papers found from arXiv.")
                return
            for paper in papers:
                authors = ", ".join(paper.authors[:3])
                print(f"{paper.title} ({paper.published or 'date unknown'})")
                print(f"  {authors}")
                print(f"  {paper.url}")
            return

        if args.command == "download":
            from finals_agent.data.paper_download import import_arxiv_paper

            document, imported = import_arxiv_paper(
                args.url,
                title=args.title,
                field=args.field,
                tags=tuple(args.tag),
                repository=repository,
            )
            if args.json:
                print(
                    json.dumps(
                        {"document": document.to_dict(), "imported": imported},
                        ensure_ascii=False,
                        indent=2,
                    )
                )
                return
            action = "Imported" if imported else "Already exists"
            print(f"{action}: {document.title} ({document.id})")
            return

        if args.command == "read":
            from finals_agent.data.workflows import PaperReadingWorkflow

            result = PaperReadingWorkflow(repository=repository).read(
                document_id=args.document_id,
                title=args.title,
                query=args.query,
                field=args.field,
                related_limit=args.related_limit,
            )
            payload = result.to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return
            data = payload["data"]
            print(f"Paper: {data['paper']['title']} ({data['paper']['id']})")
            _print_reading_state_line(data.get("reading_state"))
            if data.get("coverage"):
                coverage = data["coverage"]
                print(
                    f"Section coverage: {coverage['covered_count']}/{coverage['total_count']} "
                    f"missing={', '.join(coverage['missing_roles']) or '-'}"
                )
            print("Reading order:")
            for item in data["reading_order"][:8]:
                print(f"  - {item['step']}: {item['target']}")
            print(f"Evidence items: {len(data['evidence'])}")
            print(f"Related papers: {len(data['related_papers'])}")
            if data["next_actions"]:
                print("Next actions:")
                for item in data["next_actions"]:
                    print(f"  - {item}")
            return

        if args.command == "explain":
            from finals_agent.data.workflows import PaperReadingWorkflow

            result = PaperReadingWorkflow(repository=repository).explain(
                target=args.target,
                document_id=args.document_id,
                title=args.title,
                query=args.query,
                field=args.field,
                limit=args.limit,
            )
            payload = result.to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return
            data = payload["data"]
            print(f"Paper: {data['paper']['title']} ({data['paper']['id']})")
            _print_reading_state_line(data.get("reading_state"))
            print(f"Target: {data['target']}")
            print(f"Matched structure items: {len(data['matched_structure_candidates'])}")
            print(f"Evidence items: {len(data['evidence'])}")
            for item in data["evidence"][:3]:
                print(f"  - {item['title']} {item.get('section') or ''} page={item.get('page')}: {item['snippet']}")
            return

        if args.command == "compare":
            from finals_agent.data.workflows import PaperReadingWorkflow

            result = PaperReadingWorkflow(repository=repository).compare(
                topic=args.topic,
                document_id=args.document_id,
                title=args.title,
                query=args.query,
                field=args.field,
                related_limit=args.related_limit,
            )
            payload = result.to_dict()
            if args.json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                return
            data = payload["data"]
            print(f"Paper: {data['paper']['title']} ({data['paper']['id']})")
            _print_reading_state_line(data.get("reading_state"))
            print(f"Topic: {data['topic']}")
            print(f"Local evidence: {len(data['local_evidence'])}")
            print(f"Related papers: {len(data['related_papers'])}")
            for row in data["comparison_matrix"][:5]:
                print(f"  - {row['paper']}: {row['source']}")
            return

        if args.command == "progress":
            from finals_agent.data.selection import select_document
            from finals_agent.persistence.reading_state import ReadingStateStore, reading_state_summary

            document = select_document(
                repository,
                document_id=args.document_id,
                title=args.title,
                field=args.field,
                document_type=None,
            )
            store = ReadingStateStore()
            has_update = (
                args.status is not None
                or args.section is not None
                or args.percent is not None
                or args.summary is not None
            )
            state = (
                store.update_progress(
                    document,
                    status=args.status,
                    current_section=args.section,
                    progress_percent=args.percent,
                    review_summary=args.summary,
                )
                if has_update
                else store.get(document)
            )
            summary = reading_state_summary(state)
            if args.json:
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return
            _print_reading_state(summary)
            return

        if args.command == "note":
            from finals_agent.data.selection import select_document
            from finals_agent.persistence.reading_state import ReadingStateStore, reading_state_summary

            document = select_document(
                repository,
                document_id=args.document_id,
                title=args.title,
                field=args.field,
                document_type=None,
            )
            store = ReadingStateStore()
            if args.kind == "question":
                state = store.add_question(document, args.text, section=args.section, page=args.page, citation=args.citation)
            elif args.kind == "verification":
                state = store.add_verification_item(document, args.text, section=args.section, page=args.page, citation=args.citation)
            else:
                state = store.add_note(document, args.text, section=args.section, page=args.page, citation=args.citation)
            summary = reading_state_summary(state)
            if args.json:
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return
            _print_reading_state(summary)
            return

        if args.command == "flashcard":
            from finals_agent.data.selection import select_document
            from finals_agent.persistence.reading_state import ReadingStateStore, reading_state_summary

            document = select_document(
                repository,
                document_id=args.document_id,
                title=args.title,
                field=args.field,
                document_type=None,
            )
            state = ReadingStateStore().add_flashcard(
                document,
                question=args.question,
                answer=args.answer,
                section=args.section,
                page=args.page,
                citation=args.citation,
            )
            summary = reading_state_summary(state)
            if args.json:
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return
            _print_reading_state(summary)
            return

        if args.command == "mark":
            from finals_agent.data.selection import select_document
            from finals_agent.persistence.reading_state import ReadingStateStore, reading_state_summary

            document = select_document(
                repository,
                document_id=args.document_id,
                title=args.title,
                field=args.field,
                document_type=None,
            )
            state = ReadingStateStore().mark_item(document, item_id=args.item_id, status=args.status)
            summary = reading_state_summary(state)
            if args.json:
                print(json.dumps(summary, ensure_ascii=False, indent=2))
                return
            _print_reading_state(summary)
            return

        if args.command == "runs":
            from finals_agent.persistence.runs import JsonRunRecorder

            if args.limit < 1:
                parser.exit(status=1, message="Error: --limit must be at least 1.\n")
            records = JsonRunRecorder().list_records()[-args.limit :]
            records.reverse()
            if args.json:
                print(json.dumps(records, ensure_ascii=False, indent=2, default=str))
                return
            if not records:
                print("No agent runs recorded.")
                return
            for record in records:
                status = record.get("status", "unknown")
                task = record.get("task_type") or "-"
                duration = record.get("duration_ms")
                duration_text = f"{duration:.0f}ms" if isinstance(duration, int | float) else "-"
                question = " ".join((record.get("question") or "").split())[:100]
                print(f"{record.get('run_id')} [{status}] task={task} duration={duration_text}")
                print(f"  {question}")
            return

        if args.command == "ui":
            from finals_agent.app.web import serve_ui

            serve_ui(host=args.host, port=args.port, open_browser=args.open, app_window=args.app)
            return

        if args.command == "embed":
            from finals_agent.data.embeddings import build_document_embedding_index, build_embedding_provider

            provider = build_embedding_provider(settings.embeddings)
            if not provider.available:
                parser.exit(
                    status=1,
                    message=(
                        "Error: local embedding provider is not available. "
                        "Set EMBEDDING_PROVIDER=local and install optional dependencies with "
                        "pip install -e .[embeddings].\n"
                    ),
                )
            documents = (
                [repository.get_document(args.document_id)]
                if args.document_id
                else repository.list_documents(field=args.field)
            )
            if not documents:
                print("No local papers found.")
                return
            count = 0
            for document in documents:
                path = build_document_embedding_index(
                    document,
                    repository=repository,
                    provider=provider,
                    force=args.force,
                )
                if path:
                    count += 1
                    print(f"Embedded {document.title} ({document.id}): {path}")
            print(f"Built embedding index for {count} document(s).")
            return

        if args.command == "chat":
            from finals_agent.agent.runner import run_agent, stream_agent_events
            from finals_agent.core.schemas import AgentRequest
            from finals_agent.persistence.memory import JsonMemoryStore
            from finals_agent.persistence.runs import JsonRunRecorder

            runtime = (
                AgentRuntime.from_settings(settings.runtime)
                .with_field(args.field)
                .with_target(document_id=args.document_id, title=args.title)
                .with_debug(debug)
            )
            memory_store = JsonMemoryStore() if args.conversation_id else None
            request = AgentRequest(
                question=args.question,
                course_context=runtime.course_context,
                conversation_id=args.conversation_id,
            )
            if args.stream:
                for event in stream_agent_events(
                    request,
                    runtime=runtime,
                    memory_store=memory_store,
                    run_recorder=JsonRunRecorder(),
                ):
                    _print_stream_event(event, debug=args.debug)
                return
            result = run_agent(
                request,
                runtime=runtime,
                memory_store=memory_store,
                run_recorder=JsonRunRecorder(),
            )
            print(result.answer)
            if args.debug:
                print("\n[debug metadata]")
                print(json.dumps(result.metadata, ensure_ascii=False, indent=2, default=str))
            return

        if args.command == "evals":
            if args.suite == "llm_judge":
                from finals_agent.evals.llm_judge import run_llm_judge_evals

                results = run_llm_judge_evals(use_real_model=args.real_model, use_real_judge=args.real_judge)
            elif args.suite == "grounded":
                from finals_agent.evals.grounded_qa import run_grounded_qa_evals

                results = run_grounded_qa_evals(use_real_model=args.real_model)
            else:
                from finals_agent.evals.smoke import run_smoke_evals

                results = run_smoke_evals()
            failed = [result for result in results if not result.passed]
            for result in results:
                status = "PASS" if result.passed else "FAIL"
                score = f" score={result.score:.2f}" if hasattr(result, "score") else ""
                print(f"[{status}] {result.name}{score}: {result.reason}")
                if args.debug:
                    print(result.answer)
                    if hasattr(result, "judge_feedback"):
                        print(f"[judge] {result.judge_feedback}")
                    if hasattr(result, "judge_metadata"):
                        print(json.dumps(result.judge_metadata, ensure_ascii=False, indent=2, default=str))
            if failed:
                parser.exit(status=1, message=f"{len(failed)} eval(s) failed.\n")
            return
    except FinalsAgentError as exc:
        parser.exit(status=1, message=f"Error: {exc}\n")


def _print_stream_event(event: dict, debug: bool = False) -> None:
    if debug:
        print(json.dumps(event, ensure_ascii=False, default=str), flush=True)
        return

    name = event.get("event")
    if name == "run_started":
        print(f"[run] started task={event.get('task_type')} context={event.get('course_context')}", flush=True)
    elif name == "planning_finished":
        intent = (event.get("task_plan") or {}).get("intent", {})
        print(f"[plan] {intent.get('task_type')} retrieval={intent.get('requires_retrieval')}", flush=True)
    elif name == "preretrieval_started":
        print(f"[retrieval] searching local evidence for: {event.get('query')}", flush=True)
    elif name == "preretrieval_finished":
        print(f"[retrieval] found {event.get('count', 0)} local evidence item(s)", flush=True)
    elif name == "context_assembled":
        print(f"[context] messages={event.get('message_count')} blocks={', '.join(event.get('blocks') or [])}", flush=True)
    elif name == "agent_started":
        print("[agent] running model and tools", flush=True)
    elif name == "tool_started":
        print(f"[tool] start {event.get('tool_name')}", flush=True)
    elif name == "tool_finished":
        print(f"[tool] {event.get('status')} {event.get('tool_name')}: {event.get('message')}", flush=True)
    elif name == "agent_finished":
        print(f"[agent] completed messages={event.get('message_count')}", flush=True)
    elif name == "memory_saved":
        if event.get("enabled"):
            print(f"[memory] saved conversation={event.get('conversation_id')}", flush=True)
    elif name == "run_finished":
        print("\n[answer]", flush=True)
        print(event.get("answer", ""), flush=True)
    elif name == "run_failed":
        print(f"[error] {event.get('error')}", flush=True)
    elif name == "stream_closed":
        print(f"[stream] closed status={event.get('status')}", flush=True)


def _print_reading_state(summary: dict) -> None:
    print(f"Paper: {summary['title']} ({summary['document_id']})")
    print(
        f"Progress: {summary['status']} {summary['progress_percent']}% "
        f"section={summary.get('current_section') or '-'}"
    )
    if summary.get("review_summary"):
        print(f"Summary: {summary['review_summary']}")
    print(
        "Items: "
        f"notes={summary['note_count']}, "
        f"open_questions={summary['open_question_count']}, "
        f"open_verifications={summary['open_verification_count']}, "
        f"flashcards={summary['flashcard_count']}"
    )
    if summary.get("open_questions"):
        print("Open questions:")
        for item in summary["open_questions"]:
            print(f"  - {item['id']}: {item['text']}")
    if summary.get("open_verification_items"):
        print("Verification:")
        for item in summary["open_verification_items"]:
            print(f"  - {item['id']}: {item['text']}")
    if summary.get("recent_notes"):
        print("Recent notes:")
        for item in summary["recent_notes"]:
            print(f"  - {item['id']}: {item['text']}")
    if summary.get("recent_flashcards"):
        print("Recent flashcards:")
        for item in summary["recent_flashcards"]:
            print(f"  - {item['id']}: {item['text']} -> {item.get('answer') or ''}")


def _print_reading_state_line(summary: dict | None) -> None:
    if not summary:
        return
    print(
        "Reading state: "
        f"{summary['status']} {summary['progress_percent']}% "
        f"section={summary.get('current_section') or '-'} "
        f"open_questions={summary['open_question_count']} "
        f"open_verifications={summary['open_verification_count']} "
        f"flashcards={summary['flashcard_count']}"
    )


if __name__ == "__main__":
    main()
