from pathlib import Path

import pytest

from src.leyra_skills import activate_skill, discover_skills, read_skill_resource, skill_catalog


def write_skill(root: Path, folder: str, name: str, description: str, body: str = "Instructions.") -> Path:
    directory = root / folder
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n",
        encoding="utf-8",
    )
    return directory


def test_project_skills_are_trust_gated(tmp_path):
    project = tmp_path / "project"
    home = tmp_path / "home"
    write_skill(project / ".agents" / "skills", "project-skill", "project-skill", "Project skill")
    assert "project-skill" not in discover_skills(project, home, include_project=False)
    assert "project-skill" in discover_skills(project, home, include_project=True)


def test_project_skill_overrides_user_skill(tmp_path):
    project = tmp_path / "project"
    home = tmp_path / "home"
    write_skill(home / ".agents" / "skills", "helper", "helper", "User version")
    write_skill(project / ".agents" / "skills", "helper", "helper", "Project version")
    skills = discover_skills(project, home, include_project=True)
    assert skills["helper"].description == "Project version"


def test_catalog_contains_only_metadata(tmp_path):
    project = tmp_path / "project"
    home = tmp_path / "home"
    write_skill(home / ".agents" / "skills", "pdf", "pdf", "Process PDF files", "Long instructions")
    catalog = skill_catalog(discover_skills(project, home, include_project=False))
    assert catalog == [{"name": "pdf", "description": "Process PDF files"}]
    assert "instructions" not in catalog[0]


def test_activation_loads_body_and_lists_resources_lazily(tmp_path):
    project = tmp_path / "project"
    home = tmp_path / "home"
    directory = write_skill(home / ".agents" / "skills", "review", "review", "Review code", "Do a careful review.")
    (directory / "references").mkdir()
    (directory / "references" / "checklist.md").write_text("Checklist", encoding="utf-8")
    skills = discover_skills(project, home, include_project=False)
    activated = activate_skill("review", skills)
    assert activated["instructions"] == "Do a careful review."
    assert "references/checklist.md" in activated["resources"]


def test_resource_reader_rejects_path_traversal(tmp_path):
    project = tmp_path / "project"
    home = tmp_path / "home"
    write_skill(home / ".agents" / "skills", "safe", "safe", "Safe skill")
    skills = discover_skills(project, home, include_project=False)
    with pytest.raises(ValueError):
        read_skill_resource("safe", "../../outside.txt", skills)


def test_invalid_skill_name_is_not_activated(tmp_path):
    with pytest.raises(ValueError):
        activate_skill("../escape", {})


def test_skills_api_routes_are_registered():
    from src.leyra_gateway import router

    paths = {route.path for route in router.routes}
    assert "/leyra/v1/skills" in paths
    assert "/leyra/v1/skills/{skill_name}/activate" in paths
    assert "/leyra/v1/skills/{skill_name}/resources/{resource_path:path}" in paths



def test_chat_payload_discloses_catalog_and_registers_skill_tools(monkeypatch, tmp_path):
    from src import leyra_gateway
    from src.leyra_skills import discover_skills

    project = tmp_path / "project"
    home = tmp_path / "home"
    write_skill(home / ".agents" / "skills", "summarize", "summarize", "Summarize long text.")
    skills = discover_skills(project, home, include_project=False)
    monkeypatch.setattr(leyra_gateway, "discover_skills", lambda: skills)

    payload = leyra_gateway._prepare_skill_aware_payload({
        "model": "test-model",
        "messages": [{"role": "user", "content": "Summarize this."}],
    })

    assert payload["messages"][0]["role"] == "system"
    assert "summarize" in payload["messages"][0]["content"]
    names = {item["function"]["name"] for item in payload["tools"]}
    assert "leyra_activate_skill" in names
    assert "leyra_read_skill_resource" in names
    assert payload["tool_choice"] == "auto"


def test_chat_payload_preserves_existing_system_prompt_and_tools(monkeypatch, tmp_path):
    from src import leyra_gateway

    project = tmp_path / "project"
    home = tmp_path / "home"
    write_skill(home / ".agents" / "skills", "review", "review", "Review code.")
    skills = discover_skills(project, home, include_project=False)
    monkeypatch.setattr(leyra_gateway, "discover_skills", lambda: skills)

    payload = leyra_gateway._prepare_skill_aware_payload({
        "model": "test-model",
        "messages": [{"role": "system", "content": "Keep answers concise."},
                     {"role": "user", "content": "Review this."}],
        "tools": [{"type": "function", "function": {
            "name": "existing_tool", "description": "Existing tool",
            "parameters": {"type": "object", "properties": {}}
        }}],
    })

    assert "Keep answers concise." in payload["messages"][0]["content"]
    names = {item["function"]["name"] for item in payload["tools"]}
    assert "existing_tool" in names
    assert "leyra_activate_skill" in names


def test_local_skill_tool_activation_and_resource_read(tmp_path):
    from src.leyra_gateway import _run_local_skill_tool

    project = tmp_path / "project"
    home = tmp_path / "home"
    directory = write_skill(home / ".agents" / "skills", "docs", "docs", "Read docs.")
    (directory / "references").mkdir()
    (directory / "references" / "guide.md").write_text("Reference guide.", encoding="utf-8")

    import os
    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(home)
    try:
        activated = _run_local_skill_tool("leyra_activate_skill", '{"name":"docs"}')
        assert '"instructions": "Instructions."' in activated
        resource = _run_local_skill_tool(
            "leyra_read_skill_resource",
            '{"name":"docs","path":"references/guide.md"}',
        )
        assert "Reference guide." in resource
    finally:
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home


def test_local_skill_tool_rejects_unknown_skill():
    from src.leyra_gateway import _run_local_skill_tool

    result = _run_local_skill_tool("leyra_activate_skill", '{"name":"missing"}')
    assert '"error"' in result
