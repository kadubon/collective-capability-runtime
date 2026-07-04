from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ccr.cli import main
from ccr.schemas.validation import validate_instance


def _manifest() -> dict[str, Any]:
    return {
        "network_policy": "none",
        "non_claims": [
            "not_real_asi_proof",
            "not_execution_authority",
            "not_physical_outcome_proof",
        ],
        "provider_id": "provider:fixture",
        "provider_type": "fixture",
        "schema_version": "ccr.provider_manifest.v1",
        "settlement_policy": {
            "provider_grants_settlement": False,
            "provider_output_is_evidence_only": True,
        },
        "side_effect_policy": "read_only",
    }


def test_provider_registry_validate_and_list(tmp_path: Path, capsys: Any) -> None:
    manifest = tmp_path / "provider.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "manifest_path": "provider.json",
                        "provider_class": "static",
                        "provider_id": "provider:fixture",
                        "side_effect_class": "read_only",
                    }
                ],
                "schema_version": "ccr.provider_registry.v1",
            }
        ),
        encoding="utf-8",
    )

    assert main(["provider", "registry-validate", "--file", str(registry), "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert validate_instance("provider-registry-report", report).ok is True

    assert main(["provider", "registry-list", "--file", str(registry), "--json"]) == 0
    listing = json.loads(capsys.readouterr().out)
    assert listing["providers"][0]["provider_id"] == "provider:fixture"


def test_provider_registry_blocks_duplicate_and_unsafe_side_effect(
    tmp_path: Path, capsys: Any
) -> None:
    manifest = tmp_path / "provider.json"
    manifest.write_text(json.dumps(_manifest()), encoding="utf-8")
    registry = tmp_path / "registry.json"
    registry.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "manifest_path": "provider.json",
                        "provider_class": "static",
                        "provider_id": "provider:fixture",
                        "side_effect_class": "external_side_effect",
                    },
                    {
                        "manifest_path": "provider.json",
                        "provider_class": "static",
                        "provider_id": "provider:fixture",
                    },
                ],
                "schema_version": "ccr.provider_registry.v1",
            }
        ),
        encoding="utf-8",
    )

    assert main(["provider", "registry-validate", "--file", str(registry), "--json"]) != 0
    report = json.loads(capsys.readouterr().out)

    assert "authority_gap" in report["blockers"]
    assert "validation_error" in report["blockers"]
