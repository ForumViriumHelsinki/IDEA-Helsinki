"""Local↔CI parity checks for the lint workflow and the justfile.

CI is the authority on what a check is; the justfile recipes exist so the same
check can be run locally. These tests fail when the two drift apart — a new job
in ``lint.yml`` without a local counterpart, a recipe that stops running what its
CI job runs, or a recipe chain that skips CI's workspace sync (see #520, #522).
"""

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
JUSTFILE = REPO_ROOT / "justfile"
LINT_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "lint.yml"
PRE_COMMIT_CONFIG = REPO_ROOT / ".pre-commit-config.yaml"

# Every job in .github/workflows/lint.yml maps to the justfile recipe that runs
# the same check locally. Adding a CI job without adding it here fails
# test_every_lint_workflow_job_has_a_local_recipe.
CI_JOB_TO_RECIPE = {
    "lint": "lint",
    "type-check": "typecheck",
}

# Flags that only shape CI's output and have no bearing on what is checked.
CI_ONLY_FLAGS = {"--output-format=github", "--diff"}

RECIPE_HEADER = re.compile(r"^(?P<name>[A-Za-z0-9_-]+)(?P<params>[^:]*):(?P<deps>.*)$")


def parse_justfile(text: str) -> dict[str, dict[str, list[str]]]:
    """Parse recipe names, dependencies and body lines out of a justfile."""
    recipes: dict[str, dict[str, list[str]]] = {}
    current: str | None = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if line[0].isspace():
            if current is not None:
                recipes[current]["body"].append(line.strip())
            continue
        match = RECIPE_HEADER.match(line)
        if match is None:
            current = None
            continue
        current = match.group("name")
        recipes[current] = {
            "deps": match.group("deps").split(),
            "body": [],
        }
    return recipes


def recipe_chain(recipes: dict[str, dict[str, list[str]]], name: str) -> list[str]:
    """Return name plus all of its transitive dependencies."""
    seen: list[str] = []
    stack = [name]
    while stack:
        current = stack.pop()
        if current in seen or current not in recipes:
            continue
        seen.append(current)
        stack.extend(recipes[current]["deps"])
    return seen


def chain_commands(recipes: dict[str, dict[str, list[str]]], name: str) -> str:
    """Return every command line a recipe runs, dependencies included."""
    return "\n".join(
        line
        for recipe in recipe_chain(recipes, name)
        for line in recipes[recipe]["body"]
    )


def workflow_job_commands(job: dict) -> list[str]:
    """Return the commands a workflow job runs, stripped of CI-only flags."""
    commands: list[str] = []
    for step in job.get("steps", []):
        run = step.get("run")
        if not run:
            continue
        for line in run.splitlines():
            tokens = [t for t in line.split() if t and t not in CI_ONLY_FLAGS]
            if tokens:
                commands.append(" ".join(tokens))
    return commands


@pytest.fixture(scope="module")
def recipes() -> dict[str, dict[str, list[str]]]:
    return parse_justfile(JUSTFILE.read_text())


@pytest.fixture(scope="module")
def lint_jobs() -> dict[str, dict]:
    return yaml.safe_load(LINT_WORKFLOW.read_text())["jobs"]


@pytest.mark.unit
def test_every_lint_workflow_job_has_a_local_recipe(recipes, lint_jobs):
    assert set(lint_jobs) == set(CI_JOB_TO_RECIPE), (
        "lint.yml jobs and CI_JOB_TO_RECIPE have drifted apart — every CI job "
        "needs a justfile recipe that runs the same check locally"
    )
    for recipe in CI_JOB_TO_RECIPE.values():
        assert recipe in recipes, f"justfile has no recipe named {recipe!r}"


@pytest.mark.unit
def test_local_recipes_run_what_their_ci_job_runs(recipes, lint_jobs):
    for job_name, recipe in CI_JOB_TO_RECIPE.items():
        local = chain_commands(recipes, recipe)
        for command in workflow_job_commands(lint_jobs[job_name]):
            assert command in local, (
                f"CI job {job_name!r} runs {command!r}, but `just {recipe}` "
                f"(and its dependencies) does not"
            )


@pytest.mark.unit
def test_ci_recipe_covers_every_lint_workflow_job(recipes):
    chain = recipe_chain(recipes, "ci")
    for job_name, recipe in CI_JOB_TO_RECIPE.items():
        assert recipe in chain, (
            f"`just ci` does not run {recipe!r}, so it cannot predict the "
            f"result of CI job {job_name!r}"
        )


@pytest.mark.unit
def test_ty_pre_commit_hook_uses_the_typecheck_recipe():
    config = yaml.safe_load(PRE_COMMIT_CONFIG.read_text())
    hooks = [
        hook for repo in config["repos"] for hook in repo["hooks"] if hook["id"] == "ty"
    ]
    assert hooks, "no ty hook in .pre-commit-config.yaml"
    assert hooks[0]["entry"] == "just typecheck", (
        "the ty hook must go through the justfile recipe so there is one "
        "definition of the type check to keep in step with CI"
    )
