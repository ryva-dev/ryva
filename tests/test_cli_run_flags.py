from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from ryva.cli import app

runner = CliRunner()


def _make_project(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()
    (tmp_path / "tools").mkdir()
    (tmp_path / "pipelines").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "project.yml").write_text("name: test\nversion: '0.1.0'\n")
    (tmp_path / "target").mkdir()
    (tmp_path / "target" / "manifest.json").write_text(json.dumps({
        "ryva_version": "0.1.0",
        "project": {"name": "test"},
        "agents": {"my_agent": {"name": "my_agent", "version": "1.0.0", "description": "test"}},
        "tools": {},
        "pipelines": {},
        "prompt_hashes": {},
    }))


class TestRunInputFile:
    def test_input_file_loads_json(self, tmp_path):
        _make_project(tmp_path)
        input_file = tmp_path / "input.json"
        input_file.write_text('{"text": "hello world"}')

        with patch("ryva.runner.run_agent", return_value={"status": "success"}) as mock_run:
            runner.invoke(app, [
                "run", "--agent", "my_agent",
                "--input-file", str(input_file),
                "--root", str(tmp_path),
            ])
            mock_run.assert_called_once()
            call_args = mock_run.call_args[0]
            assert call_args[2] == {"text": "hello world"}

    def test_input_file_not_found_exits_1(self, tmp_path):
        _make_project(tmp_path)
        result = runner.invoke(app, [
            "run", "--agent", "my_agent",
            "--input-file", str(tmp_path / "nonexistent.json"),
            "--root", str(tmp_path),
        ])
        assert result.exit_code == 1

    def test_input_file_invalid_json_exits_1(self, tmp_path):
        _make_project(tmp_path)
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json at all {{{")
        result = runner.invoke(app, [
            "run", "--agent", "my_agent",
            "--input-file", str(bad_file),
            "--root", str(tmp_path),
        ])
        assert result.exit_code == 1

    def test_input_and_input_file_together_exits_1(self, tmp_path):
        _make_project(tmp_path)
        input_file = tmp_path / "input.json"
        input_file.write_text('{"text": "hi"}')
        result = runner.invoke(app, [
            "run", "--agent", "my_agent",
            "--input", '{"text": "hi"}',
            "--input-file", str(input_file),
            "--root", str(tmp_path),
        ])
        assert result.exit_code == 1


class TestRunInputDir:
    def test_input_dir_runs_against_each_file(self, tmp_path):
        _make_project(tmp_path)
        input_dir = tmp_path / "inputs"
        input_dir.mkdir()
        (input_dir / "a.json").write_text('{"text": "first"}')
        (input_dir / "b.json").write_text('{"text": "second"}')

        with patch("ryva.runner.run_agent", return_value={"status": "success"}) as mock_run:
            runner.invoke(app, [
                "run", "--agent", "my_agent",
                "--input-dir", str(input_dir),
                "--root", str(tmp_path),
            ])
            assert mock_run.call_count == 2

    def test_input_dir_empty_dir_exits_1(self, tmp_path):
        _make_project(tmp_path)
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = runner.invoke(app, [
            "run", "--agent", "my_agent",
            "--input-dir", str(empty_dir),
            "--root", str(tmp_path),
        ])
        assert result.exit_code == 1

    def test_input_dir_not_a_directory_exits_1(self, tmp_path):
        _make_project(tmp_path)
        not_a_dir = tmp_path / "file.json"
        not_a_dir.write_text("{}")
        result = runner.invoke(app, [
            "run", "--agent", "my_agent",
            "--input-dir", str(not_a_dir),
            "--root", str(tmp_path),
        ])
        assert result.exit_code == 1

    def test_input_dir_requires_agent(self, tmp_path):
        _make_project(tmp_path)
        input_dir = tmp_path / "inputs"
        input_dir.mkdir()
        (input_dir / "a.json").write_text('{"text": "hi"}')
        result = runner.invoke(app, [
            "run",
            "--input-dir", str(input_dir),
            "--root", str(tmp_path),
        ])
        assert result.exit_code == 1


class TestRunDefaultBehaviourUnchanged:
    def test_inline_input_still_works(self, tmp_path):
        _make_project(tmp_path)
        with patch("ryva.runner.run_agent", return_value={"status": "success"}) as mock_run:
            runner.invoke(app, [
                "run", "--agent", "my_agent",
                "--input", '{"text": "hello"}',
                "--root", str(tmp_path),
            ])
            mock_run.assert_called_once()
            assert mock_run.call_args[0][2] == {"text": "hello"}

    def test_no_input_defaults_to_empty_dict(self, tmp_path):
        _make_project(tmp_path)
        with patch("ryva.runner.run_agent", return_value={"status": "success"}) as mock_run:
            runner.invoke(app, [
                "run", "--agent", "my_agent",
                "--root", str(tmp_path),
            ])
            mock_run.assert_called_once()
            assert mock_run.call_args[0][2] == {}
