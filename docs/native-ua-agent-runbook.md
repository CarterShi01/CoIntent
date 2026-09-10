# Native UA Agent Runbook

**Status:** normative execution companion for CoIntent 0.4  
**Audience:** the conversational/coding Agent, not the browser user

This runbook turns the ADR decisions into one user-invisible execution path. The user only asks to register a
project, install UA, update understanding, or start design. The Agent owns the mechanics below through CoIntent
MCP and its local shell.

## 1. One-time project onboarding

1. Read the repository's canonical origin, current default branch, and preferred output language.
2. Call `project-context/register-project`. Do not upload code during registration.
3. If native UA is absent or uncertain, call `distribution/prepare-ua-installation` using facts detected by the
   Agent, execute the returned official commands, reload the Agent host, measure the checks, and call
   `distribution/verify-ua-installation`.
4. Do not continue until verification returns `ready`.

Installation and project registration never require a CoIntent executable or browser form.

## 2. Start an on-demand refresh

1. Call `understand-current/refresh-current-understanding(project_id)`.
2. In the code environment measure the repository origin, full lowercase HEAD SHA, branch, tracked/untracked
   state, installed UA revision, and the unsupported-tree flags required by preflight:

   - a mode `160000` entry means `submodules_present=true`;
   - a mode `120000` entry means `symlinks_present=true`;
   - any tracked LFS pointer means `lfs_pointers_present=true`;
   - a tracked `.gitattributes` rule using `export-ignore` or `export-subst` means
     `archive_attributes_present=true`.
3. Call `prepare-native-refresh(job_id, preflight)`. V1 stops before analysis if any unsupported-tree flag is
   true; do not conceal the flag or substitute working-tree bytes.
4. If the response says `unchanged`, do not invoke UA or domain analysis.

Never hide dirty state by omitting untracked files. If the work the user wants to understand is not committed,
ask them to commit it; a working-directory snapshot is not publishable current truth.

## 3. Analyze the frozen coordinate

For a changed coordinate, create a temporary detached worktree using standard Git:

```bash
git worktree add --detach <temporary-worktree> <frozen-revision>
```

If a checkpoint URL is present:

1. verify `git merge-base --is-ancestor <checkpoint-base> <frozen-revision>`;
2. download it with `curl --fail --location`;
3. verify its SHA-256 and byte size from the MCP response;
4. extract it at the worktree root so `.ua/` or legacy `.understand-anything/` is restored.

If ancestry fails, do not restore it. Run full and report `divergent_checkpoint` as the fallback reason.

Set `UNDERSTAND_NO_WORKTREE_REDIRECT=1`, then invoke the installed native UA Skill against the temporary worktree.
Use `--no-auto-update` and the output language in the execution plan. Surface UA's first-run `.understandignore`
review and large-repository confirmation in the Agent conversation. After a changed knowledge graph, invoke the
native domain Skill. Do not invoke the local Dashboard; CoIntent serves the pinned viewer remotely.

The actual Skill invocation syntax belongs to the Agent host (`$understand`, `/understand`, native plugin action,
or another officially supported form). CoIntent does not translate UA into a shell executable.

## 4. Package opaque artifacts

Create exactly two gzip-compressed tar archives outside the temporary worktree. Do not recreate the source tar
with a generic archiver: CoIntent requires the commit PAX marker emitted by `git archive`.

```bash
git -C <temporary-worktree> archive --format=tar.gz --output=<source-snapshot.tar.gz> <frozen-revision>
tar -C <temporary-worktree> -czf <ua-state.tar.gz> .ua
```

For a legacy project, replace `.ua` with `.understand-anything`. The UA archive must contain the whole persistent
state, including graph, domain graph, metadata, fingerprints, configuration, ignore policy, and retained scan
result. Do not fabricate missing files from the previous graph.

Measure each archive locally and call `prepare-refresh-artifacts` with exactly one `source-snapshot` and one
`ua-state` declaration containing `sha256` and `size_bytes`, plus the actual analysis mode, fallback reason, and
files reanalyzed. The response contains one short-lived URL per artifact. Transfer each archive directly:

```bash
curl --fail --location --request PUT --data-binary @<archive> '<issued-url>'
```

Archive bytes must never be pasted into chat or MCP tool arguments. If a URL expires, repeat
`prepare-refresh-artifacts` with the same declared mode and current archive digests to obtain fresh URLs.

## 5. Publish and clean up

Call `complete-native-refresh(job_id)`. Only a `completed` result with code, UA, and Observation coordinates is
published truth. An upload success by itself is only staging.

On validation failure, report the diagnostic, never repair graph JSON by hand, and leave the previous Observation
untouched. After completion or failure, remove the temporary Git worktree through the normal safe Git worktree
command. Do not trigger another scan after coding; the next explicit understanding or design request starts it.

## 6. Design remains separate

Starting design requires the latest completed root refresh. The design Agent may change expected functions and the
complete target Responsibility/Workflow graph, review its semantic diff, and create implementation context after
explicit user confirmation. That target drawing never enters the native UA upload path and is never promoted to
current truth.
