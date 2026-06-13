from pathlib import Path

import pytest

from finals_agent.core.exceptions import ToolInputError
from finals_agent.core.schemas import DocumentType
from finals_agent.data.ingestion import build_ingest_request, ingest_material
from finals_agent.data.repository import StudyRepository
from finals_agent.persistence.reading_state import ReadingStateStore, reading_state_summary
from finals_agent.persistence.storage import JsonFileStorage


def _paper(tmp_path: Path):
    source = tmp_path / "paper.md"
    source.write_text("Abstract\n\nMethod and experiments.", encoding="utf-8")
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")
    result = ingest_material(
        build_ingest_request(source, DocumentType.PAPER, "nlp", title="Target Paper"),
        repository=repository,
    )
    return result.document


def test_reading_state_store_tracks_progress_and_items(tmp_path: Path):
    document = _paper(tmp_path)
    store = ReadingStateStore(storage=JsonFileStorage(tmp_path / "reading_state.json"))

    state = store.update_progress(
        document,
        status="reading",
        current_section="2 Method",
        progress_percent=45,
        review_summary="Method pass started.",
    )
    state = store.add_note(document, "The method depends on retrieved evidence.", section="2 Method", page=3)
    state = store.add_question(document, "How is retrieval failure handled?")
    state = store.add_verification_item(document, "Verify Table 1 exact numbers.", citation="[Target Paper | page=5]")
    state = store.add_flashcard(document, question="What is the core method?", answer="Retrieve then generate.")

    summary = reading_state_summary(state)

    assert summary["status"] == "reading"
    assert summary["progress_percent"] == 45
    assert summary["note_count"] == 1
    assert summary["open_question_count"] == 1
    assert summary["open_verification_count"] == 1
    assert summary["flashcard_count"] == 1
    assert summary["recent_notes"][0]["section"] == "2 Method"


def test_reading_state_store_marks_items(tmp_path: Path):
    document = _paper(tmp_path)
    store = ReadingStateStore(storage=JsonFileStorage(tmp_path / "reading_state.json"))
    state = store.add_question(document, "What ablation proves the claim?")
    item_id = state.questions[0].id

    updated = store.mark_item(document, item_id=item_id, status="done")

    assert updated.questions[0].status == "done"
    assert updated.open_question_count == 0


def test_reading_state_store_validates_inputs(tmp_path: Path):
    document = _paper(tmp_path)
    store = ReadingStateStore(storage=JsonFileStorage(tmp_path / "reading_state.json"))

    with pytest.raises(ToolInputError, match="progress_percent"):
        store.update_progress(document, progress_percent=120)

    with pytest.raises(ToolInputError, match="current_page cannot exceed page_count"):
        store.update_progress(document, current_page=4, page_count=3)

    with pytest.raises(ToolInputError, match="answer"):
        store.add_flashcard(document, question="Q", answer="")


def test_reading_position_tracks_current_page_and_high_water_mark(tmp_path: Path):
    document = _paper(tmp_path)
    store = ReadingStateStore(storage=JsonFileStorage(tmp_path / "reading_state.json"))

    page_five = store.update_progress(document, current_page=5, page_count=10, status="reading")
    page_two = store.update_progress(document, current_page=2, page_count=10, status="reading")

    assert page_five.progress_percent == 50
    assert page_two.current_page == 2
    assert page_two.max_page_reached == 5
    assert page_two.progress_percent == 20


def test_timeline_keeps_notes_questions_and_generated_records_in_order(tmp_path: Path):
    document = _paper(tmp_path)
    store = ReadingStateStore(storage=JsonFileStorage(tmp_path / "reading_state.json"))
    store.add_note(document, "# My note")
    store.add_question(document, "What does the ablation prove?")
    updated = store.add_timeline_entry(
        document,
        "smart_reading",
        "Smart reading",
        answer="The method retrieves evidence before generation.",
        metadata={"regenerated": True},
    )
    summary = reading_state_summary(updated)

    assert [item["kind"] for item in summary["timeline"]] == [
        "note",
        "question",
        "smart_reading",
    ]
    assert summary["timeline"][-1]["metadata"]["regenerated"] is True
    assert summary["timeline"][-1]["answer"].startswith("The method")


def test_timeline_can_be_reordered_and_deleted(tmp_path: Path):
    document = _paper(tmp_path)
    store = ReadingStateStore(storage=JsonFileStorage(tmp_path / "reading_state.json"))
    first = store.add_note(document, "First note").timeline[-1]
    second = store.add_question(document, "Second question").timeline[-1]
    third = store.add_timeline_entry(document, "smart_reading", "Third record").timeline[-1]

    reordered = store.reorder_timeline(document, [third.id, first.id, second.id])
    deleted = store.delete_timeline_entry(document, first.id)

    assert [item.id for item in reordered.timeline] == [third.id, first.id, second.id]
    assert [item.id for item in deleted.timeline] == [third.id, second.id]
    assert all(item.id != first.id for item in deleted.notes)
