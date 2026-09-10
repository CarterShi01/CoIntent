from cointent.distribution import UA_REVISION, InstallationEvidence, installation_plan, verify_installation


def test_native_plan_uses_official_installer_and_exact_upstream_revision() -> None:
    plan = installation_plan("codex", "linux")
    assert "Egonex-AI/Understand-Anything" in plan["commands"][0]
    assert UA_REVISION in plan["commands"][0]
    assert plan["commands"][-1].endswith(UA_REVISION)
    assert plan["agent_action_required"] is True
    assert plan["reload_required_after_install"] is True


def test_installation_is_not_ready_until_compatible_evidence_and_reload() -> None:
    evidence = InstallationEvidence(
        platform="codex", operating_system="linux", ua_version="2.9.6", ua_revision=UA_REVISION,
        skill_path="/home/user/.agents/skills/understand", skill_manifest_present=True,
        resolved_to_ua_repository=True, git_available=True, node_major=22, pnpm_major=10,
    )
    assert verify_installation(evidence)["status"] == "installed_reload_required"
    ready = verify_installation(evidence.model_copy(update={"reload_completed": True}))
    assert ready["status"] == "ready"
    assert ready["ready"] is True


def test_installation_rejects_floating_or_colliding_install() -> None:
    evidence = InstallationEvidence(
        platform="codex", operating_system="linux", ua_version="2.9.7", ua_revision="a" * 40,
        skill_path="/tmp/understand", skill_manifest_present=True, resolved_to_ua_repository=False,
        git_available=True, node_major=20, pnpm_major=9, reload_completed=True,
    )
    result = verify_installation(evidence)
    assert result["status"] == "incompatible"
    assert len(result["problems"]) >= 4
