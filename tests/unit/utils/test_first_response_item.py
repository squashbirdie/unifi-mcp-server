"""first_response_item: the reply to a write may carry the stored object or nothing at all."""

import pytest

from src.utils import first_response_item


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ({"meta": {"rc": "ok"}, "data": [{"_id": "a"}, {"_id": "b"}]}, {"_id": "a"}),
        ([{"_id": "a"}], {"_id": "a"}),
        ({"data": {"_id": "single"}}, {"_id": "single"}),  # some routes wrap one object
        ({"data": []}, {}),  # write accepted but not echoed: must not raise IndexError
        ({}, {}),
        ([], {}),
        (None, {}),
        ("ok", {}),
        ({"data": ["junk"]}, {}),
    ],
)
def test_first_response_item(response, expected):
    assert first_response_item(response) == expected
