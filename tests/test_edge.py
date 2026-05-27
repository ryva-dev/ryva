from __future__ import annotations

import json

from ryva.edge import (
    EdgeTelemetryCollector,
    aggregate_report,
    load_all_devices,
)


class TestEdgeTelemetryCollector:
    def test_record_creates_file(self, tmp_path):
        c = EdgeTelemetryCollector(tmp_path, "device-01")
        rid = c.record("summarizer", "claude-haiku-4-5", latency_ms=120)
        assert (tmp_path / "edge_telemetry" / "device-01" / f"{rid}.json").exists()

    def test_record_returns_id(self, tmp_path):
        c = EdgeTelemetryCollector(tmp_path, "device-01")
        rid = c.record("agent", "model", 100)
        assert isinstance(rid, str) and len(rid) == 8

    def test_record_stores_all_fields(self, tmp_path):
        c = EdgeTelemetryCollector(tmp_path, "device-01")
        rid = c.record("summarizer", "claude-haiku-4-5", 250, input_tokens=50,
                       output_tokens=30, status="success", metadata={"env": "prod"})
        data = json.loads((tmp_path / "edge_telemetry" / "device-01" / f"{rid}.json").read_text())
        assert data["agent"] == "summarizer"
        assert data["latency_ms"] == 250
        assert data["input_tokens"] == 50
        assert data["metadata"]["env"] == "prod"

    def test_load_returns_all_records(self, tmp_path):
        c = EdgeTelemetryCollector(tmp_path, "device-01")
        for i in range(5):
            c.record("agent", "model", i * 10)
        assert len(c.load()) == 5

    def test_load_empty_device(self, tmp_path):
        c = EdgeTelemetryCollector(tmp_path, "nonexistent")
        assert c.load() == []

    def test_flush_deletes_all_records(self, tmp_path):
        c = EdgeTelemetryCollector(tmp_path, "device-01")
        c.record("agent", "model", 100)
        c.record("agent", "model", 200)
        n = c.flush()
        assert n == 2
        assert c.load() == []

    def test_flush_empty_returns_zero(self, tmp_path):
        c = EdgeTelemetryCollector(tmp_path, "device-01")
        assert c.flush() == 0

    def test_status_empty_device(self, tmp_path):
        c = EdgeTelemetryCollector(tmp_path, "device-01")
        s = c.status()
        assert s["record_count"] == 0
        assert s["avg_latency_ms"] is None
        assert s["device_id"] == "device-01"

    def test_status_with_records(self, tmp_path):
        c = EdgeTelemetryCollector(tmp_path, "device-01")
        c.record("agent_a", "m1", 100)
        c.record("agent_a", "m1", 200)
        c.record("agent_b", "m1", 300, status="error")
        s = c.status()
        assert s["record_count"] == 3
        assert s["avg_latency_ms"] == 200
        assert abs(s["error_rate"] - 1 / 3) < 0.01
        assert "agent_a" in s["agents"]
        assert "agent_b" in s["agents"]

    def test_status_newest_oldest(self, tmp_path):
        c = EdgeTelemetryCollector(tmp_path, "device-01")
        c.record("agent", "model", 100)
        s = c.status()
        assert s["newest_record"] is not None
        assert s["oldest_record"] is not None


class TestLoadAllDevices:
    def test_empty_returns_empty_dict(self, tmp_path):
        assert load_all_devices(tmp_path) == {}

    def test_loads_multiple_devices(self, tmp_path):
        EdgeTelemetryCollector(tmp_path, "d1").record("a", "m", 100)
        EdgeTelemetryCollector(tmp_path, "d2").record("b", "m", 200)
        devices = load_all_devices(tmp_path)
        assert "d1" in devices
        assert "d2" in devices

    def test_skips_malformed_json(self, tmp_path):
        d = tmp_path / "edge_telemetry" / "bad_device"
        d.mkdir(parents=True)
        (d / "bad.json").write_text("{broken")
        EdgeTelemetryCollector(tmp_path, "good_device").record("a", "m", 50)
        devices = load_all_devices(tmp_path)
        assert "bad_device" not in devices
        assert "good_device" in devices


class TestAggregateReport:
    def test_empty_report(self, tmp_path):
        report = aggregate_report(tmp_path)
        assert report["device_count"] == 0
        assert report["total_records"] == 0

    def test_with_records(self, tmp_path):
        EdgeTelemetryCollector(tmp_path, "d1").record("agent_a", "m", 100)
        EdgeTelemetryCollector(tmp_path, "d1").record("agent_a", "m", 300)
        EdgeTelemetryCollector(tmp_path, "d2").record("agent_b", "m", 200, status="error")
        report = aggregate_report(tmp_path)
        assert report["device_count"] == 2
        assert report["total_records"] == 3
        assert report["avg_latency_ms"] == 200
        assert "agent_a" in report["agents"]
        assert "agent_b" in report["agents"]

    def test_report_has_device_summaries(self, tmp_path):
        EdgeTelemetryCollector(tmp_path, "d1").record("a", "m", 50)
        report = aggregate_report(tmp_path)
        assert len(report["devices"]) == 1
        assert report["devices"][0]["device_id"] == "d1"
