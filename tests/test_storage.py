from finals_agent.persistence.storage import JsonFileStorage


def test_json_file_storage_round_trips_payload(tmp_path):
    storage = JsonFileStorage(tmp_path / "state.json")

    storage.write({"hello": "world"})

    assert storage.read() == {"hello": "world"}


def test_json_file_storage_returns_empty_dict_for_missing_file(tmp_path):
    storage = JsonFileStorage(tmp_path / "missing.json")

    assert storage.read() == {}


def test_json_file_storage_clear_removes_file(tmp_path):
    storage = JsonFileStorage(tmp_path / "state.json")
    storage.write({"hello": "world"})

    storage.clear()

    assert storage.read() == {}
