from __future__ import annotations

from ryva.pii_masker import apply_if_enabled, load_pii_config, mask_dict, mask_text


class TestMaskText:
    def test_masks_email(self):
        text = "Contact me at alice@example.com for details."
        masked, findings = mask_text(text, entities={"email"})
        assert "alice@example.com" not in masked
        assert len(findings) == 1
        assert findings[0]["entity"] == "email"

    def test_masks_ssn(self):
        text = "SSN: 123-45-6789 on file."
        masked, findings = mask_text(text, entities={"ssn"})
        assert "123-45-6789" not in masked
        assert len(findings) == 1
        assert findings[0]["entity"] == "ssn"

    def test_masks_phone(self):
        text = "Call me at 555-867-5309."
        masked, findings = mask_text(text, entities={"phone"})
        assert "555-867-5309" not in masked
        assert len(findings) == 1

    def test_masks_credit_card(self):
        text = "Card: 4111 1111 1111 1111"
        masked, findings = mask_text(text, entities={"credit_card"})
        assert "4111" not in masked
        assert len(findings) == 1

    def test_masks_ip_address(self):
        text = "Server at 192.168.1.100"
        masked, findings = mask_text(text, entities={"ip_address"})
        assert "192.168.1.100" not in masked
        assert len(findings) == 1

    def test_no_pii_returns_original(self):
        text = "Hello, world! Nothing sensitive here."
        masked, findings = mask_text(text)
        assert masked == text
        assert findings == []

    def test_multiple_entities_in_one_pass(self):
        text = "Email: user@test.com, SSN: 987-65-4321"
        masked, findings = mask_text(text, entities={"email", "ssn"})
        assert "user@test.com" not in masked
        assert "987-65-4321" not in masked
        assert len(findings) == 2

    def test_custom_mask_string(self):
        text = "Email: bob@corp.io"
        masked, _ = mask_text(text, entities={"email"}, mask="***")
        assert "***" in masked
        assert "bob@corp.io" not in masked

    def test_empty_entities_set_masks_nothing(self):
        text = "SSN 123-45-6789"
        masked, findings = mask_text(text, entities=set())
        assert masked == text
        assert findings == []

    def test_findings_sorted_by_position(self):
        text = "SSN: 111-22-3333 email: a@b.com"
        _, findings = mask_text(text, entities={"ssn", "email"})
        positions = [f["start"] for f in findings]
        assert positions == sorted(positions)

    def test_original_preserved_in_findings(self):
        text = "SSN: 123-45-6789"
        _, findings = mask_text(text, entities={"ssn"})
        assert findings[0]["original"] == "123-45-6789"

    def test_empty_string(self):
        masked, findings = mask_text("")
        assert masked == ""
        assert findings == []


class TestMaskDict:
    def test_masks_string_values(self):
        data = {"contact": "alice@example.com", "name": "Alice"}
        masked, findings = mask_dict(data, entities={"email"})
        assert "alice@example.com" not in str(masked)
        assert len(findings) >= 1

    def test_non_pii_dict_unchanged(self):
        data = {"key": "value", "count": 42}
        masked, findings = mask_dict(data)
        assert findings == []
        assert masked["key"] == "value"


class TestLoadPiiConfig:
    def test_disabled_by_default(self):
        cfg = load_pii_config({})
        assert cfg["enabled"] is False

    def test_enabled_when_set(self):
        project = {"pii_masking": {"enabled": True}}
        cfg = load_pii_config(project)
        assert cfg["enabled"] is True

    def test_custom_entities(self):
        project = {"pii_masking": {"enabled": True, "entities": ["email"]}}
        cfg = load_pii_config(project)
        assert cfg["entities"] == {"email"}

    def test_custom_mask_char(self):
        project = {"pii_masking": {"mask": "XXXXX"}}
        cfg = load_pii_config(project)
        assert cfg["mask"] == "XXXXX"


class TestApplyIfEnabled:
    def test_passthrough_when_disabled(self):
        project = {"pii_masking": {"enabled": False}}
        text = "SSN: 123-45-6789"
        result, findings = apply_if_enabled(text, project)
        assert result == text
        assert findings == []

    def test_masks_when_enabled(self):
        project = {"pii_masking": {"enabled": True, "entities": ["ssn"]}}
        text = "SSN: 123-45-6789"
        result, findings = apply_if_enabled(text, project)
        assert "123-45-6789" not in result
        assert len(findings) == 1

    def test_empty_project_means_disabled(self):
        text = "Email: test@example.com"
        result, findings = apply_if_enabled(text, {})
        assert result == text
        assert findings == []
