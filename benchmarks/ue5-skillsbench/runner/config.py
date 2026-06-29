"""Parse benchmark.yaml and task.toml."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

import yaml


@dataclasses.dataclass
class ProjectConfig:
    source: str
    uproject: str
    engine_association: str
    target: str
    platform: str
    configuration: str


@dataclasses.dataclass
class ConditionConfig:
    id: str
    skills: list[str]


@dataclasses.dataclass
class RunnerConfig:
    run_root: str
    trials: int
    copy_excludes: list[str]
    artifacts: list[str]


@dataclasses.dataclass
class SkillConfig:
    name: str
    path: str


@dataclasses.dataclass
class BenchmarkConfig:
    project: ProjectConfig
    skills: list[SkillConfig]
    conditions: list[ConditionConfig]
    runner: RunnerConfig


@dataclasses.dataclass
class TaskMetadata:
    difficulty: str = "medium"
    category: str = "software-engineering"
    subcategory: str = "build-repair"
    category_confidence: str = "high"
    task_type: list[str] = dataclasses.field(default_factory=list)
    modality: list[str] = dataclasses.field(default_factory=list)
    interface: list[str] = dataclasses.field(default_factory=list)
    skill_type: list[str] = dataclasses.field(default_factory=list)
    tags: list[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class TaskConfig:
    id: str
    project: str
    timeout_minutes: int = 45
    primary_skills: list[str] = dataclasses.field(default_factory=list)
    secondary_skills: list[str] = dataclasses.field(default_factory=list)
    metadata: TaskMetadata = dataclasses.field(default_factory=TaskMetadata)


def load_benchmark_yaml(path: Path) -> BenchmarkConfig:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    proj = raw["project"]
    skills_raw = raw.get("skills", {})
    skills = []
    if isinstance(skills_raw, dict):
        for name, cfg in skills_raw.items():
            skills.append(SkillConfig(name=name, path=cfg.get("path", f"skills/{name}")))
    elif isinstance(skills_raw, list):
        for name in skills_raw:
            skills.append(SkillConfig(name=name, path=f"skills/{name}"))
    return BenchmarkConfig(
        project=ProjectConfig(
            source=proj["source"],
            uproject=proj["uproject"],
            engine_association=proj["engineAssociation"],
            target=proj["target"],
            platform=proj["platform"],
            configuration=proj["configuration"],
        ),
        skills=skills,
        conditions=[
            ConditionConfig(id=c["id"], skills=c.get("skills", []))
            for c in raw.get("conditions", [])
        ],
        runner=RunnerConfig(
            run_root=raw["runner"]["runRoot"],
            trials=raw["runner"]["trials"],
            copy_excludes=raw["runner"].get("copyExcludes", []),
            artifacts=raw["runner"].get("artifacts", []),
        ),
    )


def load_task_toml(path: Path) -> TaskConfig:
    import tomllib
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    meta = raw.get("metadata", {})
    return TaskConfig(
        id=raw["id"],
        project=raw.get("project", ""),
        timeout_minutes=raw.get("timeout_minutes", 45),
        primary_skills=raw.get("primary_skills", []),
        secondary_skills=raw.get("secondary_skills", []),
        metadata=TaskMetadata(
            difficulty=meta.get("difficulty", "medium"),
            category=meta.get("category", "software-engineering"),
            subcategory=meta.get("subcategory", "build-repair"),
            category_confidence=meta.get("category_confidence", "high"),
            task_type=meta.get("task_type", []),
            modality=meta.get("modality", []),
            interface=meta.get("interface", []),
            skill_type=meta.get("skill_type", []),
            tags=meta.get("tags", []),
        ),
    )


def discover_tasks(tasks_dir: Path) -> list[TaskConfig]:
    tasks: list[TaskConfig] = []
    if not tasks_dir.exists():
        return tasks
    for task_dir in sorted(tasks_dir.iterdir()):
        toml_path = task_dir / "task.toml"
        if toml_path.exists():
            tasks.append(load_task_toml(toml_path))
    return tasks
