from cointent.models import Goal, ModelPatch, ProjectModel, RoleRecord, apply_model_patch, semantic_diff


def test_patch_produces_valid_semantic_diff() -> None:
    before = ProjectModel(project_id="demo", name="Demo")
    patch = ModelPatch(
        status="baseline",
        upsert_goals=[Goal(id="goal.ship", title="Ship")],
        upsert_roles=[RoleRecord(id="role.delivery", name="Delivery", purpose="Own delivery")],
    )
    after = apply_model_patch(before, patch)
    diff = semantic_diff(before, after)

    assert after.status == "baseline"
    assert diff["goals"]["added"] == ["goal.ship"]
    assert diff["roles"]["added"] == ["role.delivery"]
    assert diff["status_changed"] is True
