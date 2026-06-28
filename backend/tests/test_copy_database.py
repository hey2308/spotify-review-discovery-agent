from core.db_copy import normalize_copy_row


def test_normalize_copy_row_parses_json_strings() -> None:
    row = {"payload": '{"source": "social"}', "name": "plain"}
    normalized = normalize_copy_row(row)
    assert normalized["payload"] == {"source": "social"}
    assert normalized["name"] == "plain"
