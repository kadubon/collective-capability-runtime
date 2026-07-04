from __future__ import annotations

import json
from pathlib import Path

from ccr.providers.manifest import inspect_provider_manifest


def test_provider_manifest_blocks_unknown_execution_mode(tmp_path: Path) -> None:
    manifest = tmp_path / "provider.json"
    manifest.write_text(
        json.dumps(
            {
                "execution_modes": ["dynamic_shell"],
                "network_policy": "none",
                "non_claims": [
                    "not_real_asi_proof",
                    "not_execution_authority",
                    "not_physical_outcome_proof",
                ],
                "provider_id": "provider:test",
                "provider_type": "fixture",
                "schema_version": "ccr.provider_manifest.v1",
                "settlement_policy": {
                    "provider_grants_settlement": False,
                    "provider_output_is_evidence_only": True,
                },
                "side_effect_policy": "read_only",
            }
        ),
        encoding="utf-8",
    )

    report = inspect_provider_manifest(manifest)

    assert report["ok"] is False
    assert "authority_gap" in report["blockers"]


def test_provider_manifest_blocks_dynamic_import_and_bad_safe_command(tmp_path: Path) -> None:
    manifest = tmp_path / "provider.json"
    manifest.write_text(
        json.dumps(
            {
                "entrypoint": "package.module:run",
                "network_policy": "none",
                "non_claims": [
                    "not_real_asi_proof",
                    "not_execution_authority",
                    "not_physical_outcome_proof",
                ],
                "provider_id": "provider:test",
                "provider_type": "fixture",
                "safe_command_handling": {"mode": "execute_shell"},
                "schema_version": "ccr.provider_manifest.v1",
                "settlement_policy": {
                    "provider_grants_settlement": False,
                    "provider_output_is_evidence_only": True,
                },
                "side_effect_policy": "read_only",
            }
        ),
        encoding="utf-8",
    )

    report = inspect_provider_manifest(manifest)

    assert report["ok"] is False
    assert "authority_gap" in report["blockers"]
    assert "safe_command_hint" in report["blockers"]
