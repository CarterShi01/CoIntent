import pytest

from cointent.models import (
    ImplementationLink,
    ModelPatch,
    ProjectModel,
    Responsibility,
    SpecificationItem,
    SpecificationResponsibilityLink,
    Workflow,
    WorkflowEdge,
    WorkflowNode,
    apply_model_patch,
    semantic_diff,
)


def test_patch_produces_valid_v03_semantic_diff() -> None:
    before = ProjectModel(project_id="demo", name="Demo")
    patch = ModelPatch(
        status="baseline",
        upsert_specification_items=[SpecificationItem(id="spec.ship", name="Ship")],
        upsert_responsibilities=[Responsibility(
            id="responsibility.delivery", name="Deliver product", description="Deliver the accepted release.",
            inputs=["Accepted release"], outputs=["Available product"],
        )],
        upsert_specification_responsibility_links=[SpecificationResponsibilityLink(
            id="link.ship", specification_id="spec.ship", responsibility_id="responsibility.delivery",
        )],
        upsert_implementation_links=[ImplementationLink(
            id="implementation.delivery", responsibility_id="responsibility.delivery",
            artifact_path="src/delivery",
        )],
    )
    after = apply_model_patch(before, patch)
    diff = semantic_diff(before, after)

    assert after.schema_version == "0.3"
    assert after.status == "baseline"
    assert diff["specification_items"]["added"] == ["spec.ship"]
    assert diff["responsibilities"]["added"] == ["responsibility.delivery"]
    assert diff["implementation_links"]["added"] == ["implementation.delivery"]


def test_workflow_cycles_are_valid_and_dangling_nodes_are_rejected() -> None:
    children = [
        Responsibility(id="responsibility.a", name="A"),
        Responsibility(id="responsibility.b", name="B"),
    ]
    loop = Workflow(
        entry_node_ids=["a"],
        nodes=[WorkflowNode(id="a", responsibility_id="responsibility.a"),
               WorkflowNode(id="b", responsibility_id="responsibility.b")],
        edges=[WorkflowEdge(id="a-b", source_node_id="a", target_node_id="b"),
               WorkflowEdge(id="b-a", source_node_id="b", target_node_id="a", kind="condition")],
    )
    model = ProjectModel(
        project_id="demo", name="Demo",
        responsibilities=[Responsibility(id="responsibility.root", name="Root", workflow=loop), *children],
    )
    assert model.responsibilities[0].workflow.edges[-1].target_node_id == "a"

    with pytest.raises(ValueError, match="unknown responsibility"):
        ProjectModel(
            project_id="demo", name="Demo",
            responsibilities=[Responsibility(
                id="responsibility.root", name="Root",
                workflow=Workflow(entry_node_ids=["missing"], nodes=[
                    WorkflowNode(id="missing", responsibility_id="responsibility.missing"),
                ]),
            )],
        )


def test_legacy_v02_document_migrates_without_preserving_old_vocabulary() -> None:
    model = ProjectModel.model_validate({
        "schema_version": "0.2", "project_id": "demo", "name": "Demo",
        "product_functions": [{"id": "function.ship", "name": "Ship", "status": "accepted"}],
        "role_objects": [{
            "id": "role.delivery", "name": "Delivery", "purpose": "Own delivery",
            "parent_id": None, "owns_knowledge": ["Release"], "inputs": [], "outputs": [],
            "constraints": [], "source_ids": [], "status": "accepted",
        }],
        "responsibilities": [], "role_relations": [],
        "function_role_links": [{
            "id": "link.ship", "function_id": "function.ship", "role_id": "role.delivery",
            "kind": "owns", "confidence": 1, "evidence": "", "source_ids": [],
        }],
        "trace_links": [{
            "id": "trace.delivery", "role_id": "role.delivery", "artifact_path": "src/delivery",
            "kind": "realizes", "confidence": 1, "origin": "agent", "evidence": "",
        }],
    })

    assert model.schema_version == "0.3"
    assert model.specification_items[0].id == "function.ship"
    assert model.responsibilities[0].description == "Own delivery"
    assert model.implementation_links[0].responsibility_id == "role.delivery"


def test_invalid_specification_hierarchy_and_mapping_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown parent"):
        ProjectModel(project_id="demo", name="Demo", specification_items=[
            SpecificationItem(id="spec.child", name="Child", parent_id="missing"),
        ])
    with pytest.raises(ValueError, match="unknown endpoint"):
        ProjectModel(
            project_id="demo", name="Demo",
            specification_items=[SpecificationItem(id="spec.ship", name="Ship")],
            specification_responsibility_links=[SpecificationResponsibilityLink(
                id="link.ship", specification_id="spec.ship", responsibility_id="responsibility.missing",
            )],
        )
