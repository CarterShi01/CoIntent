"""Native Understand Anything distribution plans and post-install evidence checks."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


UA_VERSION = "2.9.6"
UA_REVISION = "5feed1f2ce4f9c368d860f4c0ebc36d98a4693fc"
UA_REPOSITORY = "https://github.com/Egonex-AI/Understand-Anything.git"

AgentPlatform = Literal[
    "claude", "codex", "gemini", "opencode", "pi", "openclaw", "antigravity",
    "vibe", "vscode", "hermes", "cline", "kimi", "trae", "nanobot", "kiro",
]
OperatingSystem = Literal["linux", "macos", "windows"]

INSTALLER_PLATFORMS = {
    "codex", "gemini", "opencode", "pi", "openclaw", "antigravity", "vibe",
    "vscode", "hermes", "cline", "kimi", "trae", "nanobot", "kiro",
}


class InstallationEvidence(BaseModel):
    """Facts measured by the Agent after the native installer has run."""

    model_config = ConfigDict(extra="forbid")
    platform: AgentPlatform
    operating_system: OperatingSystem
    ua_version: str
    ua_revision: str
    skill_path: str
    skill_manifest_present: bool
    resolved_to_ua_repository: bool
    git_available: bool
    node_major: int = Field(ge=0)
    pnpm_major: int = Field(ge=0)
    reload_completed: bool = False


def installation_plan(platform: AgentPlatform, operating_system: OperatingSystem) -> dict[str, Any]:
    """Return native upstream commands; never claim to execute them on the client."""

    if platform == "claude":
        commands = [
            "/plugin marketplace add Egonex-AI/Understand-Anything",
            "/plugin install understand-anything",
        ]
        pin_note = (
            "Claude's native marketplace owns installation. After reload, report the resolved plugin revision; "
            "CoIntent will reject it unless it matches the supported upstream unit."
        )
    elif platform in INSTALLER_PLATFORMS and operating_system == "windows":
        raw = f"https://raw.githubusercontent.com/Egonex-AI/Understand-Anything/{UA_REVISION}/install.ps1"
        commands = [
            f"Invoke-WebRequest {raw} -OutFile $env:TEMP\\understand-anything-install.ps1",
            f"& $env:TEMP\\understand-anything-install.ps1 {platform}",
            f"git -C $HOME/.understand-anything/repo fetch origin {UA_REVISION}",
            f"git -C $HOME/.understand-anything/repo checkout --detach {UA_REVISION}",
        ]
        pin_note = "The official installer is followed by selecting the exact unmodified supported upstream commit."
    elif platform in INSTALLER_PLATFORMS:
        raw = f"https://raw.githubusercontent.com/Egonex-AI/Understand-Anything/{UA_REVISION}/install.sh"
        commands = [
            f"curl -fsSL {raw} | bash -s -- {platform}",
            f"git -C \"$HOME/.understand-anything/repo\" fetch origin {UA_REVISION}",
            f"git -C \"$HOME/.understand-anything/repo\" checkout --detach {UA_REVISION}",
        ]
        pin_note = "The official installer is followed by selecting the exact unmodified supported upstream commit."
    else:  # defensive: Literals are not a runtime boundary for plain JSON callers
        raise ValueError(f"unsupported UA platform {platform!r}")

    return {
        "schema_version": "cointent.ua-distribution/0.1",
        "platform": platform,
        "operating_system": operating_system,
        "upstream_repository": UA_REPOSITORY,
        "supported_ua_version": UA_VERSION,
        "supported_ua_revision": UA_REVISION,
        "commands": commands,
        "pin_policy": pin_note,
        "agent_action_required": True,
        "reload_required_after_install": True,
        "post_install_checks": [
            "Resolve the installed understand Skill path and confirm SKILL.md exists.",
            "Confirm the resolved Skill belongs to the official Understand Anything checkout/plugin.",
            f"Confirm the upstream Git revision is exactly {UA_REVISION}.",
            "Confirm Git is available, Node.js major version is at least 22, and pnpm major is at least 10.",
            "Restart or reload the Agent host, then report verification evidence.",
        ],
    }


def verify_installation(evidence: InstallationEvidence) -> dict[str, Any]:
    problems: list[str] = []
    if not evidence.skill_manifest_present:
        problems.append("the resolved understand Skill has no SKILL.md")
    if not evidence.resolved_to_ua_repository:
        problems.append("the Skill path does not resolve into the official UA installation")
    if not evidence.git_available:
        problems.append("Git is unavailable")
    if evidence.node_major < 22:
        problems.append("Node.js 22 or newer is required")
    if evidence.pnpm_major < 10:
        problems.append("pnpm 10 or newer is required")
    if evidence.ua_version != UA_VERSION:
        problems.append(f"UA version {evidence.ua_version!r} is not the supported {UA_VERSION!r}")
    if not re.fullmatch(r"[0-9a-f]{40}", evidence.ua_revision):
        problems.append("UA revision is not a full lowercase Git SHA")
    elif evidence.ua_revision != UA_REVISION:
        problems.append(f"UA revision {evidence.ua_revision!r} is not supported")
    if not evidence.skill_path.strip():
        problems.append("the Agent did not report a resolved Skill path")

    ready = not problems and evidence.reload_completed
    status = "ready" if ready else ("installed_reload_required" if not problems else "incompatible")
    return {
        "schema_version": "cointent.ua-installation-verification/0.1",
        "status": status,
        "ready": ready,
        "problems": problems,
        "supported_ua_version": UA_VERSION,
        "supported_ua_revision": UA_REVISION,
        "next_action": (
            "UA is ready for an on-demand refresh."
            if ready else
            "Reload the Agent host and verify again."
            if status == "installed_reload_required" else
            "Repair the native UA installation and repeat verification."
        ),
    }
