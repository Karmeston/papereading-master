from types import SimpleNamespace

from finals_agent.agent.runner import run_agent
from finals_agent.data.repository import StudyRepository
from finals_agent.persistence.runs import JsonRunRecorder, RunRecord
from finals_agent.core.schemas import AgentRequest, AgentRunResult
from finals_agent.persistence.storage import JsonFileStorage


class FakeAgent:
    def invoke(self, payload):
        return {
            "messages": [
                SimpleNamespace(content="user message"),
                SimpleNamespace(content="agent answer"),
            ]
        }


def test_json_run_recorder_appends_records(tmp_path):
    recorder = JsonRunRecorder(JsonFileStorage(tmp_path / "runs.json"))
    record = RunRecord(
        run_id="run-1",
        status="success",
        question="hello",
        answer="hi",
        conversation_id="conv-1",
        task_type="general_chat",
        preretrieval_count=0,
        message_count=2,
        input_message_count=1,
        duration_ms=12.5,
        metadata={"trace": {"run_id": "run-1"}},
    )

    recorder.record(record)

    records = recorder.list_records()
    assert len(records) == 1
    assert records[0]["run_id"] == "run-1"
    assert records[0]["answer"] == "hi"


def test_run_record_from_agent_result():
    result = AgentRunResult(
        answer="agent answer",
        raw_messages=[],
        conversation_id="conv-1",
        metadata={
            "message_count": 2,
            "input_message_count": 1,
            "task_plan": {"intent": {"task_type": "knowledge_explanation"}},
            "preretrieval": {"count": 0},
            "trace": {"run_id": "run-1", "status": "success", "duration_ms": 10.0, "error": None},
        },
    )

    record = RunRecord.from_result(AgentRequest(question="hello", conversation_id="conv-1"), result)

    assert record.run_id == "run-1"
    assert record.question == "hello"
    assert record.answer == "agent answer"
    assert record.task_type == "knowledge_explanation"
    assert record.duration_ms == 10.0


def test_runner_records_successful_run(tmp_path):
    recorder = JsonRunRecorder(JsonFileStorage(tmp_path / "runs.json"))
    repository = StudyRepository(index_path=tmp_path / "index.json", raw_data_dir=tmp_path / "raw")

    result = run_agent(
        AgentRequest(question="explain limits", conversation_id="conv-1"),
        agent=FakeAgent(),
        repository=repository,
        run_recorder=recorder,
    )

    records = recorder.list_records()
    assert result.answer == "agent answer"
    assert len(records) == 1
    assert records[0]["question"] == "explain limits"
    assert records[0]["answer"] == "agent answer"
    assert records[0]["conversation_id"] == "conv-1"
    assert records[0]["status"] == "success"
