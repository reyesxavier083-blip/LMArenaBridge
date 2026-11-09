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



def test_skill_enable_disable_persists_and_filters_runtime_catalog(monkeypatch, tmp_path):
    from src.leyra_skills import discover_skills, managed_skill_catalog, set_skill_enabled

    project = tmp_path / "project"
    home = tmp_path / "home"
    state_file = tmp_path / "settings" / "skills.json"
    monkeypatch.setenv("LEYRA_SKILLS_STATE_FILE", str(state_file))
    write_skill(home / ".agents" / "skills", "translate", "translate", "Translate text.")

    enabled = discover_skills(project, home, include_project=False)
    assert "translate" in enabled
    set_skill_enabled("translate", False)

    runtime = discover_skills(project, home, include_project=False)
    assert "translate" not in runtime
    managed = discover_skills(project, home, include_project=False, include_disabled=True)
    assert managed_skill_catalog(managed)[0]["enabled"] is False

    set_skill_enabled("translate", True)
    assert "translate" in discover_skills(project, home, include_project=False)


def test_set_skill_enabled_rejects_invalid_names_and_non_boolean_state():
    from src.leyra_skills import set_skill_enabled

    with pytest.raises(ValueError):
        set_skill_enabled("../escape", True)
    with pytest.raises(ValueError):
        set_skill_enabled("valid-name", "yes")


def test_management_routes_are_registered():
    from src.leyra_gateway import router

    routes = {(route.path, tuple(sorted(route.methods or []))) for route in router.routes}
    assert ("/leyra/skills", ("GET",)) in routes
    assert ("/leyra/v1/skills/manage", ("GET",)) in routes
    assert ("/leyra/v1/skills/{skill_name}/state", ("PUT",)) in routes



def test_management_catalog_reports_actual_skill_scope(monkeypatch, tmp_path):
    from src.leyra_skills import discover_skills, managed_skill_catalog

    project = tmp_path / "project"
    home = tmp_path / "home"
    write_skill(home / ".agents" / "skills", "personal", "personal", "Personal skill")
    write_skill(project / ".agents" / "skills", "project-only", "project-only", "Project skill")
    monkeypatch.setenv("LEYRA_TRUST_PROJECT_SKILLS", "true")
    skills = discover_skills(project, home, include_disabled=True)
    by_name = {item["name"]: item for item in managed_skill_catalog(skills)}
    assert by_name["personal"]["scope"] == "user"
    assert by_name["project-only"]["scope"] == "project"


def test_install_skill_archive_accepts_valid_skill_zip(tmp_path):
    import io
    import zipfile
    from src.leyra_skills import install_skill_archive, discover_skills

    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("hello/SKILL.md", "---\\nname: hello\\ndescription: Hello skill\\n---\\n\\nDo useful work.")
        archive.writestr("hello/references/guide.md", "Reference.")
        archive.writestr("hello/scripts/check.py", "print('not executed')")
    result = install_skill_archive(data.getvalue(), tmp_path)
    assert result["name"] == "hello"
    skills = discover_skills(project_root=tmp_path / "project", home=tmp_path, include_project=False)
    assert "hello" in skills
    assert (tmp_path / ".agents/skills/hello/scripts/check.py").read_text() == "print('not executed')"


def test_install_skill_archive_rejects_traversal(tmp_path):
    import io
    import zipfile
    from src.leyra_skills import install_skill_archive

    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("safe/SKILL.md", "---\\nname: safe\\ndescription: Safe\\n---\\n")
        archive.writestr("safe/../../escape.txt", "nope")
    with pytest.raises(ValueError):
        install_skill_archive(data.getvalue(), tmp_path)
    assert not (tmp_path / "escape.txt").exists()


def test_install_skill_archive_rejects_duplicate_skill(tmp_path):
    import io
    import zipfile
    from src.leyra_skills import install_skill_archive

    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("repeat/SKILL.md", "---\\nname: repeat\\ndescription: Repeat\\n---\\n")
    install_skill_archive(data.getvalue(), tmp_path)
    with pytest.raises(FileExistsError):
        install_skill_archive(data.getvalue(), tmp_path)


def test_skill_install_route_is_registered():
    from src.leyra_gateway import router
    assert ("/leyra/v1/skills/install", ("POST",)) in {
        (route.path, tuple(sorted(route.methods or []))) for route in router.routes
    }
