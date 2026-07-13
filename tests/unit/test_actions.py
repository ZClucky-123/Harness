import pytest

from guarded_harness.core.actions import ActionType, parse_action


def test_parse_read_file_action():
    action = parse_action('{"type":"read_file","path":"README.md"}')

    assert action.type == ActionType.READ_FILE
    assert action.payload == {"path": "README.md"}


def test_parse_unknown_action_fails_deterministically():
    with pytest.raises(ValueError, match="unknown action type"):
        parse_action('{"type":"teleport","path":"README.md"}')


def test_parse_invalid_json_fails_deterministically():
    with pytest.raises(ValueError, match="invalid action json"):
        parse_action("{not json")
