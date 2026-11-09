"""Agent Skills discovery and progressive disclosure for LEYRA IA.

Implements the portable Agent Skills folder convention without requiring PyYAML.
Project skills are trust-gated; user-level skills are available by default.
"""
from __future__ import annotations

import os
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_DEPTH = 5
MAX_DIRECTORIES = 2000
MAX_SKILLS = 500
MAX_RESOURCE_FILES = 100
MAX_SKILL_BYTES = 1024 * 1024
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


@dataclass(frozen=True)
class Skill:
    name: str
    description: str
    location: Path
    body: str
    metadata: dict[str, str]

    @property
    def directory(self) -> Path:
        return self.location.parent


def _parse_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    if not raw.startswith("---\n") and not raw.startswith("---\r\n"):
        raise ValueError("SKILL.md must start with YAML frontmatter.")
    lines = raw.splitlines()
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("YAML frontmatter closing delimiter is missing.") from exc
    header = lines[1:end]
    body = "\n".join(lines[end + 1:]).strip()
    # Prefer a real YAML parser when the host already provides one.
    try:
        import yaml  # type: ignore[import-not-found]
        data = yaml.safe_load("\n".join(header)) or {}
        if not isinstance(data, dict):
            raise ValueError("Frontmatter must be a YAML mapping.")
        return data, body
    except ImportError:
        pass
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in header:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[:1].isspace() and current_key == "metadata":
            key, sep, value = line.strip().partition(":")
            if sep:
                data.setdefault("metadata", {})[key.strip()] = value.strip().strip("'\\\"")
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError("Malformed YAML frontmatter.")
        key = key.strip()
        value = value.strip()
        current_key = key
        if not value:
            data[key] = {}
        elif value.startswith(("|", ">")):
            data[key] = value
        else:
            data[key] = value.strip("'\\\"")
    return data, body


def _read_skill(skill_file: Path) -> Skill:
    if skill_file.is_symlink() or not skill_file.is_file():
        raise ValueError("SKILL.md must be a regular file.")
    if skill_file.stat().st_size > MAX_SKILL_BYTES:
        raise ValueError("SKILL.md exceeds the 1 MiB safety limit.")
    raw = skill_file.read_text(encoding="utf-8")
    data, body = _parse_frontmatter(raw)
    name = data.get("name")
    description = data.get("description")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name) or len(name) > 64:
        raise ValueError("Skill name is missing or invalid.")
    if not isinstance(description, str) or not description.strip() or len(description) > 1024:
        raise ValueError("Skill description is missing or invalid.")
    if name != skill_file.parent.name:
        warnings.warn(
            f"Skill name '{name}' does not match directory '{skill_file.parent.name}'.",
            RuntimeWarning,
            stacklevel=2,
        )
    metadata = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
    metadata = {str(k): str(v) for k, v in metadata.items()}
    if metadata.get("disable-model-invocation", "").lower() == "true":
        metadata["model-invocation-disabled"] = "true"
    return Skill(name, description.strip(), skill_file.resolve(), body, metadata)


def _candidate_roots(project_root: Path, home: Path) -> list[tuple[Path, str]]:
    roots: list[tuple[Path, str]] = []
    for relative in (".agents/skills", ".leyra/skills", ".claude/skills"):
        roots.append((home / relative, "user"))
    extra = os.getenv("LEYRA_SKILLS_PATHS", "")
    for item in extra.split(os.pathsep):
        if item.strip():
            roots.append((Path(item).expanduser(), "user"))
    # Trusted project roots are scanned last so they always win collisions.
    for relative in (".agents/skills", ".leyra/skills", ".claude/skills"):
        roots.append((project_root / relative, "project"))
    return roots


def _iter_skill_files(root: Path):
    if not root.is_dir() or root.is_symlink():
        return
    visited = 0
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        depth = len(current_path.relative_to(root).parts)
        dirs[:] = [
            name for name in dirs
            if name not in SKIP_DIRS and not name.startswith(".") and
            not (current_path / name).is_symlink()
        ]
        visited += len(dirs)
        if visited > MAX_DIRECTORIES:
            warnings.warn(f"Skill scan limit reached under {root}.", RuntimeWarning, stacklevel=2)
            dirs[:] = []
        if depth >= MAX_DEPTH:
            dirs[:] = []
        if "SKILL.md" in files:
            yield current_path / "SKILL.md"


def discover_skills(
    project_root: str | Path | None = None,
    home: str | Path | None = None,
    include_project: bool | None = None,
) -> dict[str, Skill]:
    """Discover skills; project scope is disabled until explicitly trusted."""
    project = Path(project_root or os.getenv("LEYRA_PROJECT_ROOT") or Path.cwd()).expanduser().resolve()
    user_home = Path(home or Path.home()).expanduser().resolve()
    if include_project is None:
        include_project = os.getenv("LEYRA_TRUST_PROJECT_SKILLS", "false").lower() in {
            "1", "true", "yes", "on"
        }
    found: dict[str, Skill] = {}
    # User-level entries are loaded first; trusted project-level entries override them.
    for root, scope in _candidate_roots(project, user_home):
        if scope == "project" and not include_project:
            continue
        for skill_file in _iter_skill_files(root) or ():
            try:
                skill = _read_skill(skill_file)
            except (OSError, UnicodeError, ValueError) as exc:
                warnings.warn(f"Skipping invalid skill at {skill_file}: {exc}", RuntimeWarning, stacklevel=2)
                continue
            if skill.metadata.get("model-invocation-disabled") == "true":
                continue
            if skill.name in found:
                warnings.warn(
                    f"Skill collision for '{skill.name}'; {scope}-level skill takes precedence.",
                    RuntimeWarning,
                    stacklevel=2,
                )
            found[skill.name] = skill
            if len(found) >= MAX_SKILLS:
                warnings.warn("LEYRA skill catalog limit reached.", RuntimeWarning, stacklevel=2)
                return found
    return found


def skill_catalog(skills: dict[str, Skill] | None = None) -> list[dict[str, str]]:
    skills = skills if skills is not None else discover_skills()
    return [
        {"name": skill.name, "description": skill.description}
        for skill in sorted(skills.values(), key=lambda item: item.name)
    ]


def _resource_files(skill: Skill) -> list[str]:
    result: list[str] = []
    for current, dirs, files in os.walk(skill.directory, followlinks=False):
        current_path = Path(current)
        dirs[:] = [
            name for name in dirs
            if name not in SKIP_DIRS and not (current_path / name).is_symlink()
        ]
        for filename in sorted(files):
            path = current_path / filename
            if filename == "SKILL.md" or path.is_symlink():
                continue
            relative = path.relative_to(skill.directory).as_posix()
            if len(Path(relative).parts) <= 4:
                result.append(relative)
            if len(result) >= MAX_RESOURCE_FILES:
                return result
    return sorted(result)


def activate_skill(name: str, skills: dict[str, Skill] | None = None) -> dict[str, Any]:
    """Load tier-2 instructions and enumerate (but do not read) tier-3 resources."""
    if not NAME_RE.fullmatch(name):
        raise ValueError("Invalid skill name.")
    available = skills if skills is not None else discover_skills()
    skill = available.get(name)
    if skill is None:
        raise KeyError(name)
    return {
        "name": skill.name,
        "description": skill.description,
        "instructions": skill.body,
        "skill_directory": str(skill.directory),
        "resources": _resource_files(skill),
    }


def read_skill_resource(name: str, relative_path: str, skills: dict[str, Skill] | None = None) -> str:
    """Read one referenced resource while preventing traversal and symlink escapes."""
    if not NAME_RE.fullmatch(name):
        raise ValueError("Invalid skill name.")
    available = skills if skills is not None else discover_skills()
    skill = available.get(name)
    if skill is None:
        raise KeyError(name)
    candidate = (skill.directory / relative_path).resolve()
    try:
        candidate.relative_to(skill.directory.resolve())
    except ValueError as exc:
        raise ValueError("Resource path escapes the skill directory.") from exc
    if candidate.is_symlink() or not candidate.is_file():
        raise FileNotFoundError(relative_path)
    if candidate.stat().st_size > MAX_SKILL_BYTES:
        raise ValueError("Skill resource exceeds the 1 MiB safety limit.")
    return candidate.read_text(encoding="utf-8")
