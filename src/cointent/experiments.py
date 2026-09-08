"""Curated experiment baselines built from scanner evidence."""

from __future__ import annotations

from .models import Goal, ProjectModel, Relation, Responsibility, RoleRecord, TraceLink
from .scanner import RepositorySnapshot


def idea_factory_model(snapshot: RepositorySnapshot) -> ProjectModel:
    """Return the first agent-produced responsibility model for Idea Factory.

    The model is intentionally curated rather than claimed as deterministic truth.
    Its trace links are grounded in the supplied scan and remain reviewable.
    """

    evidence = [f"scan:{snapshot.id}"]
    goals = [
        Goal(id="goal.screen-ideas", title="产出经过筛选的创业想法",
             description="把多类信号转化为每日候选创业想法，并给出判断与低成本的下一步验证。",
             source_ids=evidence),
        Goal(id="goal.cost-gradient", title="沿漏斗逐步投入判断成本",
             description="前段使用低成本的确定性筛选，只对存活候选投入昂贵的语义判断。",
             parent_id="goal.screen-ideas", source_ids=evidence),
        Goal(id="goal.explainability", title="让每个决策都可解释",
             description="保留证据、评分、结论与反馈，使结果能够被审查并持续改进。",
             parent_id="goal.screen-ideas", source_ids=evidence),
    ]
    roles = [
        RoleRecord(id="role.idea-factory", name="想法工厂", parent_id=None,
                   purpose="负责把信号端到端地转化为经过筛选、可以验证的创业想法。", source_ids=evidence),
        RoleRecord(id="role.signal-intelligence", name="信号情报", parent_id="role.idea-factory",
                   purpose="获取、标准化、交叉验证并压缩嘈杂的来源信号。", source_ids=evidence),
        RoleRecord(id="role.candidate-generation", name="候选生成", parent_id="role.idea-factory",
                   purpose="生成多样化的想法候选，并使用具有时效性的因子进行排序。", source_ids=evidence),
        RoleRecord(id="role.evaluation-gate", name="评估关卡", parent_id="role.idea-factory",
                   purpose="高效淘汰薄弱候选，产出有依据的结论和下一步验证。", source_ids=evidence),
        RoleRecord(id="role.learning-loop", name="学习闭环", parent_id="role.idea-factory",
                   purpose="记录结果与反馈，用于校准后续评分和决策。", source_ids=evidence),
        RoleRecord(id="role.domain-contract", name="共享领域契约", parent_id="role.idea-factory",
                   purpose="维持系统中模型、因子、LLM 边界、状态和证据语义的一致性。", source_ids=evidence),
        RoleRecord(id="role.operator-surface", name="操作界面", parent_id="role.idea-factory",
                   purpose="让创始人查看漏斗、运行流程，并记录决策与结果。", source_ids=evidence),
        RoleRecord(id="role.workflow-mirror", name="工作流镜像", parent_id="role.idea-factory",
                   purpose="把选定的流水线行为镜像到外部运行的 Dify 工作流，同时保持核心契约不变。", source_ids=evidence),
    ]
    responsibilities = [
        Responsibility(id="resp.signal-acquisition", role_id="role.signal-intelligence",
                       statement="通过隔离且可替换的来源适配器，采集三类信号。",
                       goal_ids=["goal.screen-ideas"], outputs=["标准化来源记录"], source_ids=evidence),
        Responsibility(id="resp.signal-reduction", role_id="role.signal-intelligence",
                       statement="在生成候选前，对信号进行标准化、去重、初筛和交叉验证。",
                       goal_ids=["goal.cost-gradient"], inputs=["原始信号"], outputs=["合格信号"], source_ids=evidence),
        Responsibility(id="resp.generate", role_id="role.candidate-generation",
                       statement="生成多个候选，并计算可比较且随时间衰减的因子分数。",
                       goal_ids=["goal.screen-ideas", "goal.cost-gradient"], inputs=["合格信号"], outputs=["已排序候选"], source_ids=evidence),
        Responsibility(id="resp.evaluate", role_id="role.evaluation-gate",
                       statement="执行硬性门槛、证据检查、对抗性判断与组合筛选。",
                       goal_ids=["goal.screen-ideas", "goal.cost-gradient"], inputs=["已排序候选"], outputs=["结论与决策备忘"], source_ids=evidence),
        Responsibility(id="resp.next-test", role_id="role.evaluation-gate",
                       statement="为存活想法附上风险最高的假设和一个低成本、有边界的实验。",
                       goal_ids=["goal.screen-ideas"], outputs=["可验证的下一步行动"], source_ids=evidence),
        Responsibility(id="resp.learn", role_id="role.learning-loop",
                       statement="记录结果、提炼经验，并根据观察到的预测误差建议校准调整。",
                       goal_ids=["goal.explainability"], inputs=["结论与结果"], outputs=["校准证据"], source_ids=evidence),
        Responsibility(id="resp.contract", role_id="role.domain-contract",
                       statement="定义各 Role 共用的候选、证据、因子、账本、状态与 LLM 契约。",
                       goal_ids=["goal.explainability"], outputs=["稳定的共享语义"], source_ids=evidence),
        Responsibility(id="resp.operate", role_id="role.operator-surface",
                       statement="展示流水线状态，并为运行、反馈和结果提供经过认证的人类控制。",
                       goal_ids=["goal.explainability"], inputs=["模型与流水线输出"], outputs=["人类决策"], source_ids=evidence),
        Responsibility(id="resp.mirror", role_id="role.workflow-mirror",
                       statement="维护经过明确验证的生成与评估工作流镜像。",
                       goal_ids=["goal.explainability"], source_ids=evidence),
    ]
    relations = [
        Relation(id="rel.signal-to-generation", source_role_id="role.signal-intelligence",
                 target_role_id="role.candidate-generation", kind="exchanges_with", label="合格信号"),
        Relation(id="rel.generation-to-evaluation", source_role_id="role.candidate-generation",
                 target_role_id="role.evaluation-gate", kind="exchanges_with", label="已排序候选"),
        Relation(id="rel.evaluation-to-learning", source_role_id="role.evaluation-gate",
                 target_role_id="role.learning-loop", kind="exchanges_with", label="结论与结果"),
        Relation(id="rel.all-to-contract", source_role_id="role.candidate-generation",
                 target_role_id="role.domain-contract", kind="depends_on", label="模型与因子"),
        Relation(id="rel.eval-to-contract", source_role_id="role.evaluation-gate",
                 target_role_id="role.domain-contract", kind="depends_on", label="模型与证据"),
        Relation(id="rel.surface-to-roles", source_role_id="role.operator-surface",
                 target_role_id="role.evaluation-gate", kind="collaborates", label="审查与控制"),
        Relation(id="rel.mirror-to-generation", source_role_id="role.workflow-mirror",
                 target_role_id="role.candidate-generation", kind="depends_on", label="镜像契约"),
    ]
    trace_links = [
        _trace("signal", "role.signal-intelligence", "src/idea_gen/collect.py", snapshot),
        _trace("sources", "role.signal-intelligence", "src/idea_gen/sources", snapshot),
        _trace("generation", "role.candidate-generation", "src/idea_gen/generate.py", snapshot),
        _trace("ranking", "role.candidate-generation", "src/idea_gen/ranks.py", snapshot),
        _trace("evaluation", "role.evaluation-gate", "src/idea_eval", snapshot),
        _trace("learning", "role.learning-loop", "src/idea_eval/retro.py", snapshot),
        _trace("calibration", "role.learning-loop", "src/idea_eval/calibrate.py", snapshot),
        _trace("contract", "role.domain-contract", "src/idea_core", snapshot),
        _trace("studio-server", "role.operator-surface", "studio/server", snapshot, kind="presents"),
        _trace("studio-web", "role.operator-surface", "studio/web", snapshot, kind="presents"),
        _trace("dify", "role.workflow-mirror", "dify", snapshot),
    ]
    return ProjectModel(
        project_id=snapshot.project_id,
        name="想法工厂",
        summary="一个描述如何把来源信号转化为经过筛选的创业想法和有边界实验的责任模型。",
        status="baseline",
        goals=goals,
        roles=roles,
        responsibilities=responsibilities,
        relations=relations,
        trace_links=trace_links,
    )


def _trace(
    suffix: str, role_id: str, artifact_path: str, snapshot: RepositorySnapshot,
    *, kind: str = "realizes",
) -> TraceLink:
    known = {item.path for item in snapshot.artifacts}
    exists = artifact_path in known or any(path.startswith(f"{artifact_path.rstrip('/')}/") for path in known)
    return TraceLink(
        id=f"trace.{suffix}", role_id=role_id, artifact_path=artifact_path,
        kind=kind, confidence=0.96 if exists else 0.55, origin="agent",
        evidence=f"源自 {snapshot.id}；扫描中{'已观察到' if exists else '未观察到'}该路径。",
    )
