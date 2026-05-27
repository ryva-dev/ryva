from __future__ import annotations

from ryva.vision_lineage import (
    compute_agreement,
    generate_vision_report,
    hash_image_bytes,
    lineage_for_image,
    record_annotation,
    record_inference,
)

# ---------------------------------------------------------------------------
# Image hashing
# ---------------------------------------------------------------------------

class TestHashImageBytes:
    def test_returns_sha256_prefix(self):
        h = hash_image_bytes(b"hello world")
        assert h.startswith("sha256:")

    def test_deterministic(self):
        data = b"test image data"
        assert hash_image_bytes(data) == hash_image_bytes(data)

    def test_different_bytes_different_hash(self):
        assert hash_image_bytes(b"imageA") != hash_image_bytes(b"imageB")

    def test_empty_bytes(self):
        h = hash_image_bytes(b"")
        assert h.startswith("sha256:")


# ---------------------------------------------------------------------------
# record_inference
# ---------------------------------------------------------------------------

class TestRecordInference:
    def test_creates_file(self, tmp_path):
        rid = record_inference(
            tmp_path,
            image_hash="sha256:abc123",
            model="yolov8",
            predictions=[{"label": "cat", "confidence": 0.95}],
        )
        assert (tmp_path / "vision_lineage" / f"{rid}.json").exists()

    def test_returns_record_id(self, tmp_path):
        rid = record_inference(tmp_path, image_hash="sha256:abc")
        assert isinstance(rid, str) and len(rid) == 8

    def test_stores_predictions(self, tmp_path):
        import json
        rid = record_inference(
            tmp_path,
            image_hash="sha256:abc",
            predictions=[{"label": "dog", "confidence": 0.8}],
        )
        data = json.loads((tmp_path / "vision_lineage" / f"{rid}.json").read_text())
        assert data["predictions"][0]["label"] == "dog"
        assert data["type"] == "inference"

    def test_hashes_image_file(self, tmp_path):
        img = tmp_path / "test.png"
        img.write_bytes(b"\x89PNG fake image data")
        import json
        rid = record_inference(tmp_path, image_path=img)
        data = json.loads((tmp_path / "vision_lineage" / f"{rid}.json").read_text())
        assert data["image_hash"].startswith("sha256:")


# ---------------------------------------------------------------------------
# record_annotation
# ---------------------------------------------------------------------------

class TestRecordAnnotation:
    def test_creates_file(self, tmp_path):
        rid = record_annotation(
            tmp_path,
            image_hash="sha256:abc",
            annotator="alice",
            labels=[{"label": "cat"}],
        )
        assert (tmp_path / "vision_lineage" / f"{rid}.json").exists()

    def test_stores_annotator(self, tmp_path):
        import json
        rid = record_annotation(tmp_path, image_hash="sha256:x", annotator="bob")
        data = json.loads((tmp_path / "vision_lineage" / f"{rid}.json").read_text())
        assert data["annotator"] == "bob"
        assert data["type"] == "annotation"

    def test_links_to_inference(self, tmp_path):
        import json
        inf_id = record_inference(tmp_path, image_hash="sha256:y")
        ann_id = record_annotation(tmp_path, image_hash="sha256:y", inference_id=inf_id)
        data = json.loads((tmp_path / "vision_lineage" / f"{ann_id}.json").read_text())
        assert data["inference_id"] == inf_id


# ---------------------------------------------------------------------------
# compute_agreement
# ---------------------------------------------------------------------------

class TestComputeAgreement:
    def test_exact_match(self, tmp_path):
        inf_id = record_inference(
            tmp_path, image_hash="sha256:a",
            predictions=[{"label": "cat"}, {"label": "dog"}],
        )
        ann_id = record_annotation(
            tmp_path, image_hash="sha256:a",
            labels=[{"label": "cat"}, {"label": "dog"}],
        )
        result = compute_agreement(inf_id, ann_id, tmp_path)
        assert result["agreement_score"] is not None
        assert result["agreement_score"] > 0.9

    def test_no_overlap(self, tmp_path):
        inf_id = record_inference(
            tmp_path, image_hash="sha256:b",
            predictions=[{"label": "airplane"}],
        )
        ann_id = record_annotation(
            tmp_path, image_hash="sha256:b",
            labels=[{"label": "bicycle"}],
        )
        result = compute_agreement(inf_id, ann_id, tmp_path)
        assert result["agreement_score"] is not None
        assert result["agreement_score"] <= 0.5

    def test_missing_record_returns_error(self, tmp_path):
        result = compute_agreement("ghost1", "ghost2", tmp_path)
        assert result["agreement_score"] is None
        assert "error" in result

    def test_empty_predictions_and_labels(self, tmp_path):
        inf_id = record_inference(tmp_path, image_hash="sha256:c")
        ann_id = record_annotation(tmp_path, image_hash="sha256:c")
        result = compute_agreement(inf_id, ann_id, tmp_path)
        assert result["agreement_score"] == 1.0

    def test_result_has_required_fields(self, tmp_path):
        inf_id = record_inference(tmp_path, image_hash="sha256:d",
                                  predictions=[{"label": "cat"}])
        ann_id = record_annotation(tmp_path, image_hash="sha256:d",
                                   labels=[{"label": "cat"}])
        result = compute_agreement(inf_id, ann_id, tmp_path)
        for field in ("inference_id", "annotation_id", "agreement_score",
                      "matched", "only_inference", "only_annotation"):
            assert field in result


# ---------------------------------------------------------------------------
# lineage_for_image
# ---------------------------------------------------------------------------

class TestLineageForImage:
    def test_empty_returns_empty(self, tmp_path):
        assert lineage_for_image(tmp_path, "sha256:abc") == []

    def test_returns_records_for_hash(self, tmp_path):
        record_inference(tmp_path, image_hash="sha256:img1", model="yolo")
        record_annotation(tmp_path, image_hash="sha256:img1", annotator="alice")
        record_inference(tmp_path, image_hash="sha256:other", model="yolo")
        records = lineage_for_image(tmp_path, "sha256:img1")
        assert len(records) == 2
        assert all(r["image_hash"] == "sha256:img1" for r in records)

    def test_sorted_by_timestamp(self, tmp_path):
        for _ in range(3):
            record_inference(tmp_path, image_hash="sha256:t", model="m")
        records = lineage_for_image(tmp_path, "sha256:t")
        timestamps = [r["timestamp"] for r in records]
        assert timestamps == sorted(timestamps)


# ---------------------------------------------------------------------------
# generate_vision_report
# ---------------------------------------------------------------------------

class TestGenerateVisionReport:
    def test_empty_report(self, tmp_path):
        report = generate_vision_report(tmp_path)
        assert report["total_records"] == 0
        assert report["inferences"] == 0
        assert report["annotations"] == 0

    def test_counts_records(self, tmp_path):
        record_inference(tmp_path, image_hash="sha256:a", model="yolo")
        record_inference(tmp_path, image_hash="sha256:b", model="yolo")
        record_annotation(tmp_path, image_hash="sha256:a", annotator="alice")
        report = generate_vision_report(tmp_path)
        assert report["total_records"] == 3
        assert report["inferences"] == 2
        assert report["annotations"] == 1

    def test_unique_images(self, tmp_path):
        record_inference(tmp_path, image_hash="sha256:x", model="m")
        record_inference(tmp_path, image_hash="sha256:x", model="m")
        record_inference(tmp_path, image_hash="sha256:y", model="m")
        report = generate_vision_report(tmp_path)
        assert report["unique_images"] == 2

    def test_models_and_annotators(self, tmp_path):
        record_inference(tmp_path, image_hash="sha256:a", model="yolov8")
        record_annotation(tmp_path, image_hash="sha256:a", annotator="bob")
        report = generate_vision_report(tmp_path)
        assert "yolov8" in report["models"]
        assert "bob" in report["annotators"]
