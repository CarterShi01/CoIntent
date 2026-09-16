from cointent.distribution import (
    PRIVATE_UNDERSTAND_MANIFEST,
    UA_REVISION,
    InstallationEvidence,
    installation_plan,
    verify_installation,
)


def test_native_plan_uses_private_checkout_and_exact_upstream_revision() -> None:
    plan = installation_plan("codex", "linux")
    commands = "\n".join(plan["commands"])
    assert "git clone --no-checkout https://github.com/Egonex-AI/Understand-Anything.git" in commands
    assert UA_REVISION in commands
    assert "install.sh" not in commands
    assert "ln -s" not in commands
    assert "rm -- \"$cointent_ua_link\"" in commands
    assert plan["private_runtime_root"].endswith(f"/ua/{UA_REVISION}")
    assert plan["private_manifests"]["understand"].endswith(PRIVATE_UNDERSTAND_MANIFEST)
    assert plan["agent_action_required"] is True
    assert plan["reload_required_after_install"] is True


def test_installation_is_not_ready_until_compatible_evidence_and_reload() -> None:
    evidence = InstallationEvidence(
        platform="codex", operating_system="linux", ua_version="2.9.6", ua_revision=UA_REVISION,
        runtime_root=f"/home/user/.cointent/runtime/ua/{UA_REVISION}",
        skill_path=f"/home/user/.cointent/runtime/ua/{UA_REVISION}/{PRIVATE_UNDERSTAND_MANIFEST}",
        skill_manifest_present=True, resolved_to_ua_repository=True,
        global_skill_catalog_checked=True, global_ua_skill_links=[],
        git_available=True, node_major=22, pnpm_major=10,
    )
    assert verify_installation(evidence)["status"] == "installed_reload_required"
    ready = verify_installation(evidence.model_copy(update={"reload_completed": True}))
    assert ready["status"] == "ready"
    assert ready["ready"] is True


def test_installation_rejects_floating_or_colliding_install() -> None:
    evidence = InstallationEvidence(
        platform="codex", operating_system="linux", ua_version="2.9.7", ua_revision="a" * 40,
        runtime_root="/tmp/ua/floating", skill_path="/tmp/understand", skill_manifest_present=True,
        resolved_to_ua_repository=False, global_skill_catalog_checked=False,
        global_ua_skill_links=["/home/user/.agents/skills/understand"],
        git_available=True, node_major=20, pnpm_major=9, reload_completed=True,
    )
    result = verify_installation(evidence)
    assert result["status"] == "incompatible"
    assert len(result["problems"]) >= 4


def test_installation_rejects_remaining_global_ua_skill_links() -> None:
    evidence = InstallationEvidence(
        platform="codex", operating_system="linux", ua_version="2.9.6", ua_revision=UA_REVISION,
        runtime_root=f"/home/user/.cointent/runtime/ua/{UA_REVISION}",
        skill_path=f"/home/user/.cointent/runtime/ua/{UA_REVISION}/{PRIVATE_UNDERSTAND_MANIFEST}",
        skill_manifest_present=True, resolved_to_ua_repository=True,
        global_skill_catalog_checked=True,
        global_ua_skill_links=["/home/user/.agents/skills/understand"],
        git_available=True, node_major=22, pnpm_major=10, reload_completed=True,
    )
    result = verify_installation(evidence)
    assert result["status"] == "incompatible"
    assert "UA links remain in the host global Skill catalog" in result["problems"]
