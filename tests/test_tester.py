from __future__ import annotations
import pytest
from ryva.tester import _check_schema


class TestCheckSchema:
    def test_correct_types(self):
        output = {"name": "Alice", "score": 0.95, "items": [1, 2, 3], "active": True}
        expect = {
            "name": {"type": "str"},
            "score": {"type": "float"},
            "items": {"type": "list"},
            "active": {"type": "bool"},
        }
        passed, detail = _check_schema(output, expect)
        assert passed is True

    def test_missing_field(self):
        passed, detail = _check_schema({"name": "Alice"}, {"missing_field": {"type": "str"}})
        assert passed is False
        assert "missing_field" in detail

    def test_wrong_type(self):
        passed, detail = _check_schema({"count": "not-an-int"}, {"count": {"type": "int"}})
        assert passed is False
        assert "count" in detail

    def test_min_length_pass(self):
        passed, _ = _check_schema(
            {"summary": "This is long enough."},
            {"summary": {"type": "str", "min_length": 10}},
        )
        assert passed is True

    def test_min_length_fail(self):
        passed, detail = _check_schema(
            {"summary": "short"},
            {"summary": {"type": "str", "min_length": 20}},
        )
        assert passed is False
        assert "too short" in detail

    def test_range_pass(self):
        passed, _ = _check_schema(
            {"confidence": 0.75},
            {"confidence": {"type": "float", "range": [0.0, 1.0]}},
        )
        assert passed is True

    def test_range_fail_above(self):
        passed, detail = _check_schema(
            {"confidence": 1.5},
            {"confidence": {"type": "float", "range": [0.0, 1.0]}},
        )
        assert passed is False
        assert "out of range" in detail

    def test_range_fail_below(self):
        passed, detail = _check_schema(
            {"score": -0.1},
            {"score": {"type": "float", "range": [0.0, 1.0]}},
        )
        assert passed is False
        assert "out of range" in detail

    def test_range_boundary_inclusive(self):
        passed, _ = _check_schema({"v": 0.0}, {"v": {"type": "float", "range": [0.0, 1.0]}})
        assert passed is True
        passed, _ = _check_schema({"v": 1.0}, {"v": {"type": "float", "range": [0.0, 1.0]}})
        assert passed is True

    def test_nested_field_via_output_prefix(self):
        output = {"result": {"text": "hello"}}
        passed, _ = _check_schema(output, {"output.result.text": {"type": "str"}})
        assert passed is True

    def test_nested_field_missing(self):
        output = {"result": {}}
        passed, detail = _check_schema(output, {"output.result.text": {"type": "str"}})
        assert passed is False

    def test_empty_expect_always_passes(self):
        passed, _ = _check_schema({"anything": "goes"}, {})
        assert passed is True

    def test_int_field(self):
        passed, _ = _check_schema({"count": 42}, {"count": {"type": "int"}})
        assert passed is True

    def test_dict_field(self):
        passed, _ = _check_schema({"meta": {"k": "v"}}, {"meta": {"type": "dict"}})
        assert passed is True
