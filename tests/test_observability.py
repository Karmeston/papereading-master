from finals_agent.core.observability import RunObserver


def test_run_observer_records_success_trace():
    observer = RunObserver(run_id="run-1")
    observer.start(course_context="course=calculus")
    trace = observer.finish(message_count=2)

    assert trace.run_id == "run-1"
    assert trace.status == "success"
    assert trace.duration_ms >= 0
    assert trace.metadata["course_context"] == "course=calculus"
    assert trace.metadata["message_count"] == 2
    assert trace.error is None


def test_run_observer_records_error_trace():
    observer = RunObserver(run_id="run-2")
    observer.start()
    trace = observer.fail(ValueError("bad input"))

    assert trace.run_id == "run-2"
    assert trace.status == "error"
    assert trace.duration_ms >= 0
    assert trace.error == "ValueError: bad input"
