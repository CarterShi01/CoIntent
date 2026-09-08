import pytest

from cointent.models import (
    FunctionRoleLink,
    Goal,
    ModelPatch,
    ProductFunction,
    ProjectModel,
    RoleObject,
    RoleRecord,
    apply_model_patch,
    semantic_diff,
)


def test_patch_produces_valid_v02_semantic_diff() -> None:
    before = ProjectModel(project_id="demo", name="Demo")
    patch = ModelPatch(
        name="Demo product",
        status="baseline",
        upsert_product_functions=[ProductFunction(id="function.ship", name="Ship")],
        upsert_role_objects=[RoleObject(id="role.delivery", name="Delivery", purpose="Own delivery")],
        upsert_function_role_links=[FunctionRoleLink(
            id="link.ship", function_id="function.ship", role_id="role.delivery", kind="owns",
        )],
    )
    after = apply_model_patch(before, patch)
    diff = semantic_diff(before, after)

    assert after.schema_version == "0.2"
    assert after.status == "baseline"
    assert diff["product_functions"]["added"] == ["function.ship"]
    assert diff["role_objects"]["added"] == ["role.delivery"]
    assert diff["function_role_links"]["added"] == ["link.ship"]
    assert diff["status_changed"] is True


def test_legacy_python_objects_and_patch_names_normalize_to_v02() -> None:
    model = ProjectModel(
        schema_version="0.1",
        project_id="demo",
        name="Demo",
        goals=[Goal(id="goal.ship", title="Ship", status="open")],
        roles=[RoleRecord(id="role.delivery", name="Delivery", purpose="Own delivery")],
    )
    patch = ModelPatch(upsert_goals=[Goal(id="goal.learn", title="Learn")])

    assert model.schema_version == "0.2"
    assert model.product_functions[0].name == "Ship"
    assert model.product_functions[0].status == "questioned"
    assert apply_model_patch(model, patch).product_functions[-1].id == "goal.learn"


def test_invalid_hierarchy_and_mapping_endpoints_are_rejected() -> None:
    with pytest.raises(ValueError, match="unknown parent"):
        ProjectModel(
            project_id="demo", name="Demo",
            product_functions=[ProductFunction(id="function.child", name="Child", parent_id="missing")],
        )
    with pytest.raises(ValueError, match="unknown endpoint"):
        ProjectModel(
            project_id="demo", name="Demo",
            product_functions=[ProductFunction(id="function.ship", name="Ship")],
            function_role_links=[FunctionRoleLink(
                id="link.ship", function_id="function.ship", role_id="role.missing", kind="owns",
            )],
        )
