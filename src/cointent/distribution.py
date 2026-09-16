"""Native Understand Anything distribution plans and post-install evidence checks."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


UA_VERSION = "2.9.6"
UA_REVISION = "5feed1f2ce4f9c368d860f4c0ebc36d98a4693fc"
UA_REPOSITORY = "https://github.com/Egonex-AI/Understand-Anything.git"
PRIVATE_RUNTIME_SUFFIX = f".cointent/runtime/ua/{UA_REVISION}"
PRIVATE_UNDERSTAND_MANIFEST = "understand-anything-plugin/skills/understand/SKILL.md"
PRIVATE_DOMAIN_MANIFEST = "understand-anything-plugin/skills/understand-domain/SKILL.md"

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
    runtime_root: str
    skill_path: str
    skill_manifest_present: bool
    resolved_to_ua_repository: bool
    global_skill_catalog_checked: bool
    global_ua_skill_links: list[str] = Field(default_factory=list)
    git_available: bool
    node_major: int = Field(ge=0)
    pnpm_major: int = Field(ge=0)
    reload_completed: bool = False


def installation_plan(platform: AgentPlatform, operating_system: OperatingSystem) -> dict[str, Any]:
    """Return private native-runtime commands; never execute client-local commands."""

    if operating_system == "windows":
        runtime_root = f"$env:USERPROFILE\\{PRIVATE_RUNTIME_SUFFIX.replace('/', '\\')}"
        commands = [
            f"New-Item -ItemType Directory -Force -Path (Split-Path -Parent '{runtime_root}') | Out-Null",
            (
                f"if (Test-Path '{runtime_root}\\.git') {{ git -C '{runtime_root}' remote set-url origin {UA_REPOSITORY} }} "
                f"else {{ git clone --no-checkout {UA_REPOSITORY} '{runtime_root}' }}"
            ),
            f"git -C '{runtime_root}' fetch origin {UA_REVISION}",
            f"git -C '{runtime_root}' checkout --detach {UA_REVISION}",
            (
                "$legacy = Join-Path $env:USERPROFILE '.understand-anything\\repo\\understand-anything-plugin\\skills'; "
                "$private = '" + runtime_root + "\\understand-anything-plugin\\skills'; "
                "$catalog = Join-Path $env:USERPROFILE '.agents\\skills'; "
                "if (Test-Path $catalog) { Get-ChildItem -Path $catalog -Filter 'understand*' | "
                "Where-Object { $_.LinkType -and ((Resolve-Path $_.FullName).Path.StartsWith($legacy) -or "
                "(Resolve-Path $_.FullName).Path.StartsWith($private)) } | Remove-Item -Force }"
            ),
        ]
    elif platform in INSTALLER_PLATFORMS or platform == "claude":
        runtime_root = f"$HOME/{PRIVATE_RUNTIME_SUFFIX}"
        commands = [
            f"mkdir -p \"$HOME/.cointent/runtime/ua\"",
            (
                f"if [ -d \"{runtime_root}/.git\" ]; then git -C \"{runtime_root}\" remote set-url origin {UA_REPOSITORY}; "
                f"else git clone --no-checkout {UA_REPOSITORY} \"{runtime_root}\"; fi"
            ),
            f"git -C \"{runtime_root}\" fetch origin {UA_REVISION}",
            f"git -C \"{runtime_root}\" checkout --detach {UA_REVISION}",
            (
                "for cointent_ua_link in \"$HOME/.agents/skills\"/understand*; do "
                "[ -L \"$cointent_ua_link\" ] || continue; "
                "cointent_ua_target=$(readlink -f \"$cointent_ua_link\" 2>/dev/null || true); "
                "case \"$cointent_ua_target\" in "
                "\"$HOME/.understand-anything/repo/understand-anything-plugin/skills/\"*|"
                "\"$HOME/.cointent/runtime/ua/\"*/understand-anything-plugin/skills/*) "
                "rm -- \"$cointent_ua_link\" ;; esac; done"
            ),
        ]
    else:  # defensive: Literals are not a runtime boundary for plain JSON callers
        raise ValueError(f"unsupported UA platform {platform!r}")

    return {
        "schema_version": "cointent.ua-distribution/0.1",
        "platform": platform,
        "operating_system": operating_system,
        "upstream_repository": UA_REPOSITORY,
        "supported_ua_version": UA_VERSION,
        "supported_ua_revision": UA_REVISION,
        "private_runtime_root": runtime_root,
        "private_manifests": {
            "understand": f"{runtime_root}/{PRIVATE_UNDERSTAND_MANIFEST}",
            "understand_domain": f"{runtime_root}/{PRIVATE_DOMAIN_MANIFEST}",
        },
        "commands": commands,
        "pin_policy": (
            "Clone the exact unmodified upstream unit into CoIntent's private runtime. "
            "Do not run the upstream platform installer: it registers UA as a global Agent Skill."
        ),
        "agent_action_required": True,
        "reload_required_after_install": True,
        "post_install_checks": [
            "Resolve the private understand manifest path and confirm SKILL.md exists.",
            "Confirm the resolved manifest belongs to the private pinned Understand Anything checkout.",
            "Confirm no understand* symbolic link remains in the host global Skill catalog.",
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
        problems.append("the manifest path does not resolve into the official UA checkout")
    runtime_root = _normalized_path(evidence.runtime_root)
    skill_path = _normalized_path(evidence.skill_path)
    expected_manifest = f"{runtime_root}/{PRIVATE_UNDERSTAND_MANIFEST}"
    if not runtime_root.endswith(f"/ua/{UA_REVISION}"):
        problems.append("the UA runtime root is not CoIntent's pinned private runtime")
    if skill_path != expected_manifest:
        problems.append("the resolved understand manifest is not inside the private CoIntent runtime")
    if "/.agents/skills/" in skill_path:
        problems.append("the resolved understand manifest is still exposed through the global Skill catalog")
    if not evidence.global_skill_catalog_checked:
        problems.append("the Agent did not check the host global Skill catalog")
    if evidence.global_ua_skill_links:
        problems.append("UA links remain in the host global Skill catalog")
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


def _normalized_path(value: str) -> str:
    return value.strip().replace("\\", "/").rstrip("/")
