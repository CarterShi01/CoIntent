import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { fetchSession, loadWorkspace, login, logout } from "./api";
import type { Finding, ModelResponse, OverviewResponse, Proposal, RoleRecord } from "./types";

type Workspace = { model: ModelResponse; overview: OverviewResponse; findings: Finding[]; proposals: Proposal[] };
type Auth = { state: "checking" } | { state: "out" } | { state: "in"; user: string | null };

function App() {
  const [auth, setAuth] = useState<Auth>({ state: "checking" });
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [selectedRole, setSelectedRole] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [mobileView, setMobileView] = useState<"book" | "map">("book");

  useEffect(() => {
    fetchSession()
      .then((session) => setAuth(session.authed ? { state: "in", user: session.user } : { state: "out" }))
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  useEffect(() => {
    if (auth.state !== "in") return;
    loadWorkspace()
      .then((next) => {
        setWorkspace(next);
        setSelectedRole(
          next.model.model.roles.find((role) => role.parent_id !== null)?.id
            ?? next.model.model.roles[0]?.id
            ?? "",
        );
      })
      .catch((reason: unknown) => {
        if (reason instanceof Error && reason.message.startsWith("401 ")) setAuth({ state: "out" });
        else setError(reason instanceof Error ? reason.message : String(reason));
      });
  }, [auth.state]);

  if (error) return <Failure message={error} />;
  if (auth.state === "checking") return <Loading label="正在检查访问权限…" />;
  if (auth.state === "out") return <LoginScreen onDone={(user) => setAuth({ state: "in", user })} />;
  if (!workspace) return <Loading label="正在打开责任模型…" />;

  const { model: response, overview, findings, proposals } = workspace;
  const model = response.model;
  const selected = model.roles.find((role) => role.id === selectedRole) ?? model.roles[0];
  const shortRevision = overview.latest_snapshot?.revision.slice(0, 8) ?? "尚未扫描";

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <IntentMark />
          <div>
            <div className="brand">CoIntent</div>
            <div className="brand-subtitle">意图 ↔ 实现</div>
          </div>
        </div>
        <div className="project-identity">
          <span className="eyebrow">观察项目</span>
          <strong>{model.name}</strong>
        </div>
        <div className="topbar-meta">
          <Meta label="模型" value={`v${response.version} · ${statusLabel(model.status)}`} tone="blue" />
          <Meta label="代码" value={`${shortRevision}${overview.latest_snapshot?.dirty ? " · 有未提交改动" : ""}`} />
          <Meta label="对齐" value={`${overview.counts.open_findings} 项待处理`} tone={overview.counts.open_findings ? "amber" : "mint"} />
          <button className="session-button" onClick={() => {
            void logout().finally(() => {
              setWorkspace(null);
              setAuth({ state: "out" });
            });
          }}>{auth.user ?? "carter"} · 退出</button>
        </div>
      </header>

      <nav className="mobile-tabs" aria-label="工作区视图">
        <button className={mobileView === "book" ? "active" : ""} onClick={() => setMobileView("book")}>Role 说明书</button>
        <button className={mobileView === "map" ? "active" : ""} onClick={() => setMobileView("map")}>系统图谱</button>
      </nav>

      <main className="workspace">
        <section className={`book-pane ${mobileView === "book" ? "mobile-active" : ""}`}>
          <div className="pane-heading">
            <div>
              <span className="eyebrow">期望系统</span>
              <h1>责任说明书</h1>
            </div>
            <span className="version-stamp">基线 / {response.version}</span>
          </div>

          <p className="thesis">{model.summary}</p>

          <section className="goal-section">
            <SectionLabel index="A" title="目标" count={model.goals.length} />
            <div className="goal-thread">
              {model.goals.map((goal) => (
                <article className="goal" key={goal.id}>
                  <span className="goal-node" aria-hidden="true" />
                  <div>
                    <strong>{goal.title}</strong>
                    <p>{goal.description}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="role-section">
            <SectionLabel index="B" title="责任主体" count={model.roles.length} />
            <RoleTree roles={model.roles} selected={selectedRole} onSelect={setSelectedRole} />
          </section>

          {selected && (
            <section className="role-detail" aria-live="polite">
              <div className="detail-kicker">当前 Role</div>
              <h2>{selected.name}</h2>
              <p className="role-purpose">{selected.purpose}</p>
              <div className="responsibilities">
                {model.responsibilities.filter((item) => item.role_id === selected.id).map((item, index) => (
                  <div className="responsibility" key={item.id}>
                    <span>{String(index + 1).padStart(2, "0")}</span>
                    <p>{item.statement}</p>
                  </div>
                ))}
              </div>
              <div className="artifact-list">
                <span className="eyebrow">实现证据</span>
                {model.trace_links.filter((link) => link.role_id === selected.id).map((link) => (
                  <code key={link.id}>{link.artifact_path}</code>
                ))}
                {!model.trace_links.some((link) => link.role_id === selected.id) && <em>尚无实现映射。</em>}
              </div>
            </section>
          )}
        </section>

        <section className={`map-pane ${mobileView === "map" ? "mobile-active" : ""}`}>
          <div className="pane-heading map-heading">
            <div>
              <span className="eyebrow">系统投影</span>
              <h1>Role 拓扑</h1>
            </div>
            <div className="legend"><span className="legend-line" /> 包含 <span className="legend-dash" /> 协作</div>
          </div>
          <RoleGraph roles={model.roles} relations={model.relations} selected={selectedRole} onSelect={setSelectedRole} />
          <AlignmentRail findings={findings} proposals={proposals} roles={model.roles} onSelectRole={setSelectedRole} />
        </section>
      </main>
    </div>
  );
}

function IntentMark() {
  return <svg className="intent-mark" viewBox="0 0 42 42" aria-hidden="true">
    <path d="M7 9h10l8 12 10 12" />
    <path d="M7 33h10l8-12L35 9" />
    <circle cx="7" cy="9" r="3" /><circle cx="7" cy="33" r="3" /><circle cx="25" cy="21" r="3.5" /><circle cx="35" cy="9" r="3" /><circle cx="35" cy="33" r="3" />
  </svg>;
}

function Meta({ label, value, tone = "neutral" }: { label: string; value: string; tone?: string }) {
  return <div className={`meta meta-${tone}`}><span>{label}</span><strong>{value}</strong></div>;
}

function SectionLabel({ index, title, count }: { index: string; title: string; count: number }) {
  return <div className="section-label"><span>{index}</span><strong>{title}</strong><em>{count}</em></div>;
}

function RoleTree({ roles, selected, onSelect }: { roles: RoleRecord[]; selected: string; onSelect: (id: string) => void }) {
  const children = useMemo(() => {
    const map = new Map<string | null, RoleRecord[]>();
    roles.forEach((role) => map.set(role.parent_id, [...(map.get(role.parent_id) ?? []), role]));
    return map;
  }, [roles]);
  const render = (parent: string | null, depth: number) => (children.get(parent) ?? []).map((role) => (
    <div key={role.id}>
      <button className={`role-row ${selected === role.id ? "selected" : ""}`} style={{ "--depth": depth } as CSSProperties} onClick={() => onSelect(role.id)}>
        <span className="role-index">{depth === 0 ? "根" : `第 ${depth} 层`}</span>
        <span>{role.name}</span>
        <span className="role-state">{statusLabel(role.status)}</span>
      </button>
      {render(role.id, depth + 1)}
    </div>
  ));
  return <div className="role-tree">{render(null, 0)}</div>;
}

type PositionedRole = RoleRecord & { x: number; y: number; width: number; height: number };

function RoleGraph({ roles, relations, selected, onSelect }: {
  roles: RoleRecord[];
  relations: { id: string; source_role_id: string; target_role_id: string; label: string }[];
  selected: string;
  onSelect: (id: string) => void;
}) {
  const positioned = useMemo<PositionedRole[]>(() => {
    const roots = roles.filter((role) => !role.parent_id);
    const children = roles.filter((role) => role.parent_id);
    const output: PositionedRole[] = roots.map((role, index) => ({ ...role, x: 30, y: 76 + index * 140, width: 170, height: 88 }));
    children.forEach((role, index) => output.push({ ...role, x: 250 + (index % 2) * 250, y: 28 + Math.floor(index / 2) * 132, width: 205, height: 94 }));
    return output;
  }, [roles]);
  const byId = new Map(positioned.map((role) => [role.id, role]));
  const height = Math.max(560, ...positioned.map((role) => role.y + role.height + 60));
  return <div className="graph-frame">
    <div className="graph-coordinate">ROLE 模型 / 责任尺度</div>
    <div className="graph-canvas" style={{ height }}>
      <svg width="100%" height={height} aria-hidden="true">
        <defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto"><path d="M0,0 L0,6 L7,3 z" /></marker></defs>
        {positioned.filter((role) => role.parent_id).map((role) => {
          const parent = byId.get(role.parent_id!); if (!parent) return null;
          return <path className={`intent-edge ${selected === role.id || selected === parent.id ? "active" : ""}`} key={`parent-${role.id}`}
            d={`M${parent.x + parent.width},${parent.y + parent.height / 2} C${parent.x + parent.width + 50},${parent.y + parent.height / 2} ${role.x - 55},${role.y + role.height / 2} ${role.x},${role.y + role.height / 2}`} />;
        })}
        {relations.map((relation) => {
          const source = byId.get(relation.source_role_id); const target = byId.get(relation.target_role_id);
          if (!source || !target) return null;
          return <path className={`relation-edge ${selected === source.id || selected === target.id ? "active" : ""}`} key={relation.id}
            markerEnd="url(#arrow)" d={`M${source.x + source.width / 2},${source.y + source.height} C${source.x + source.width / 2},${source.y + source.height + 40} ${target.x + target.width / 2},${target.y - 40} ${target.x + target.width / 2},${target.y}`} />;
        })}
      </svg>
      {positioned.map((role) => (
        <button key={role.id} className={`graph-node ${selected === role.id ? "selected" : ""} ${role.parent_id ? "" : "root"}`}
          style={{ left: role.x, top: role.y, width: role.width, minHeight: role.height }} onClick={() => onSelect(role.id)}>
          <span>{role.parent_id ? "ROLE" : "系统"}</span><strong>{role.name}</strong><p>{role.purpose}</p>
        </button>
      ))}
    </div>
  </div>;
}

function AlignmentRail({ findings, proposals, roles, onSelectRole }: {
  findings: Finding[];
  proposals: Proposal[];
  roles: RoleRecord[];
  onSelectRole: (id: string) => void;
}) {
  return <aside className="alignment-rail">
    <div className="rail-title"><span className="pulse" /> 对齐审查 <em>{findings.length} 项偏差 · {proposals.length} 项提案</em></div>
    {proposals.map((proposal) => <ProposalCard key={proposal.id} proposal={proposal} />)}
    {findings.length === 0 ? <p className="all-clear">当前扫描没有发现挑战已接受模型的开放偏差。</p> : findings.slice(0, 4).map((finding) => (
      <button key={finding.id} className={`finding severity-${finding.severity}`} onClick={() => finding.role_ids[0] && onSelectRole(finding.role_ids[0])}>
        <span>{findingKindLabel(finding.kind)}</span><strong>{finding.summary}</strong><small>{finding.role_ids.map((id) => roles.find((role) => role.id === id)?.name ?? id).join(" · ") || "尚未映射"}</small>
      </button>
    ))}
  </aside>;
}

function ProposalCard({ proposal }: { proposal: Proposal }) {
  const sections: [string, keyof Pick<Proposal["diff"], "goals" | "roles" | "responsibilities" | "relations" | "trace_links">][] = [
    ["目标", "goals"], ["Role", "roles"], ["职责", "responsibilities"], ["关系", "relations"], ["实现映射", "trace_links"],
  ];
  const changes = sections.flatMap(([label, key]) => {
    const value = proposal.diff[key];
    return [
      ...value.added.map((id) => `${label} + ${id}`),
      ...value.changed.map((id) => `${label} ~ ${id}`),
      ...value.removed.map((id) => `${label} − ${id}`),
    ];
  });
  return <article className="proposal-card">
    <div><span>待审提案</span><code>{proposal.id}</code></div>
    <strong>{proposal.rationale}</strong>
    <p>{changes.join(" · ") || "仅修改项目名称、模型摘要或状态"}</p>
    <small>基于 v{proposal.base_version} · 请在 Agent 中明确接受或拒绝</small>
  </article>;
}

function LoginScreen({ onDone }: { onDone: (user: string) => void }) {
  const [user, setUser] = useState("carter");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  return <main className="login-screen">
    <section className="login-context" aria-label="CoIntent 介绍">
      <div className="login-brand"><IntentMark /><span>CoIntent</span></div>
      <div className="login-thread" aria-hidden="true"><i /><i /><i /><i /></div>
      <span className="eyebrow">人的意图 / Agent 的实现</span>
      <h1>在责任尺度上<br />看见整个系统。</h1>
      <p>目标逐步形成 Role，Role 持续映射实现，每一次被接受的变化都保留证据。</p>
    </section>
    <section className="login-gate">
      <form onSubmit={(event) => {
        event.preventDefault();
        setBusy(true);
        setMessage("");
        void login(user, password)
          .then((result) => onDone(result.user))
          .catch((reason: unknown) => setMessage(reason instanceof Error && reason.message.startsWith("429 ")
            ? "尝试次数过多，请等待几分钟后重试。"
            : "用户名或密码不正确。"))
          .finally(() => setBusy(false));
      }}>
        <span className="eyebrow">私有工作区</span>
        <h2>进入责任模型</h2>
        <p>人的登录会话与 Agent 使用的 MCP 凭证相互独立。</p>
        <label>用户名<input name="username" autoComplete="username" value={user} onChange={(event) => setUser(event.target.value)} /></label>
        <label>密码<input name="password" type="password" autoComplete="current-password" autoFocus value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        {message && <div className="login-error" role="alert">{message}</div>}
        <button type="submit" disabled={busy || !user || !password}>{busy ? "正在验证…" : "打开 CoIntent"}<span>→</span></button>
        <small>签名会话 · HttpOnly · SameSite Strict · 7 天</small>
      </form>
    </section>
  </main>;
}

function Loading({ label }: { label: string }) {
  return <div className="state-screen"><IntentMark /><span>{label}</span></div>;
}

function Failure({ message }: { message: string }) {
  return <div className="state-screen failure"><IntentMark /><h1>无法打开模型。</h1><p>{message}</p><button onClick={() => location.reload()}>重试</button></div>;
}

function statusLabel(status: string) {
  return ({ baseline: "基线", draft: "草案", accepted: "已接受", questioned: "待确认", open: "开放", deferred: "暂缓" } as Record<string, string>)[status] ?? status;
}

function findingKindLabel(kind: string) {
  return ({ convergent: "一致", absent: "缺失", divergent: "偏离", boundary_change: "边界变化", unmapped: "未映射", uncertain: "不确定", accepted_exception: "已接受例外" } as Record<string, string>)[kind] ?? kind;
}

export default App;
