"""Versioned prompt loading, rendering, and SHA-256 verification."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping


_PLACEHOLDER = re.compile(r"\{\{([A-Z][A-Z0-9_]*)\}\}")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class PromptIntegrityError(RuntimeError):
    """Raised when a prompt differs from its committed hash or escapes the repo."""


@dataclass(frozen=True)
class PromptSpec:
    """Pinned identity for one prompt file."""

    name: str
    version: str
    path: Path
    sha256: str


def repository_root() -> Path:
    """Return the repository root inferred from this installed source tree."""

    return Path(__file__).resolve().parents[3]


def sha256_file(path: str | Path) -> str:
    """Hash a file without normalizing line endings or text encoding."""

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_agent_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load the agentic configuration without supplying invented defaults."""

    selected = (
        Path(path)
        if path is not None
        else repository_root() / "config" / "agentic_validation.json"
    )
    with selected.open("r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        raise ValueError("agentic validation config must be a JSON object")
    for required in ("model", "investigation_budget", "source_policy", "prompts"):
        if required not in loaded:
            raise ValueError(f"agentic validation config missing {required!r}")
    return loaded


def _within_root(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def get_prompt_spec(
    name: str,
    *,
    config: Mapping[str, Any] | None = None,
    root: str | Path | None = None,
) -> PromptSpec:
    """Resolve one configured prompt while preventing path traversal."""

    loaded = config if config is not None else load_agent_config()
    prompt_table = loaded.get("prompts")
    if not isinstance(prompt_table, Mapping) or name not in prompt_table:
        raise KeyError(f"unknown configured prompt: {name}")
    raw = prompt_table[name]
    if not isinstance(raw, Mapping):
        raise ValueError(f"prompt config for {name!r} must be an object")
    for field in ("version", "path", "sha256"):
        if not isinstance(raw.get(field), str) or not raw[field]:
            raise ValueError(f"prompt {name!r} has invalid {field}")
    expected_hash = raw["sha256"].lower()
    if _SHA256.fullmatch(expected_hash) is None:
        raise ValueError(f"prompt {name!r} sha256 must contain 64 lowercase hex digits")

    base = Path(root).resolve() if root is not None else repository_root().resolve()
    relative_path = Path(raw["path"])
    if relative_path.is_absolute():
        raise PromptIntegrityError("prompt paths must be repository-relative")
    resolved = (base / relative_path).resolve()
    if not _within_root(resolved, base):
        raise PromptIntegrityError("prompt path escapes the repository root")
    if f"_{raw['version']}.md" != resolved.name[-(len(raw["version"]) + 4) :]:
        raise PromptIntegrityError(
            f"prompt version {raw['version']!r} does not match filename {resolved.name!r}"
        )
    return PromptSpec(name, raw["version"], resolved, expected_hash)


def load_prompt(
    name: str,
    *,
    verify: bool = True,
    config: Mapping[str, Any] | None = None,
    root: str | Path | None = None,
) -> str:
    """Load a prompt and, by default, require its configured hash to match."""

    spec = get_prompt_spec(name, config=config, root=root)
    actual_hash = sha256_file(spec.path)
    if verify and actual_hash != spec.sha256:
        raise PromptIntegrityError(
            f"prompt hash mismatch for {name}: expected {spec.sha256}, got {actual_hash}"
        )
    return spec.path.read_text(encoding="utf-8")


def verify_prompt_hashes(
    *,
    config: Mapping[str, Any] | None = None,
    root: str | Path | None = None,
) -> dict[str, str]:
    """Verify every configured prompt and return its observed SHA-256 hash."""

    loaded = config if config is not None else load_agent_config()
    prompt_table = loaded.get("prompts")
    if not isinstance(prompt_table, Mapping):
        raise ValueError("prompts config must be an object")
    observed: dict[str, str] = {}
    for name in sorted(prompt_table):
        spec = get_prompt_spec(name, config=loaded, root=root)
        actual = sha256_file(spec.path)
        if actual != spec.sha256:
            raise PromptIntegrityError(
                f"prompt hash mismatch for {name}: expected {spec.sha256}, got {actual}"
            )
        observed[name] = actual
    return observed


def prompt_manifest(
    *,
    config: Mapping[str, Any] | None = None,
    root: str | Path | None = None,
) -> list[dict[str, str]]:
    """Return auditable version/path/hash records after integrity verification."""

    loaded = config if config is not None else load_agent_config()
    observed = verify_prompt_hashes(config=loaded, root=root)
    result: list[dict[str, str]] = []
    for name in sorted(observed):
        spec = get_prompt_spec(name, config=loaded, root=root)
        base = Path(root).resolve() if root is not None else repository_root().resolve()
        result.append(
            {
                "name": name,
                "version": spec.version,
                "path": spec.path.relative_to(base).as_posix(),
                "prompt_hash": observed[name],
            }
        )
    return result


def canonical_json(value: Any) -> str:
    """Encode structured prompt data deterministically."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def render_prompt(
    name: str,
    values: Mapping[str, Any],
    *,
    config: Mapping[str, Any] | None = None,
    root: str | Path | None = None,
) -> str:
    """Render only declared placeholders, JSON-encoding non-string values.

    Placeholder replacement is literal rather than ``str.format`` based, so
    braces inside untrusted values cannot be interpreted as template syntax.
    """

    template = load_prompt(name, config=config, root=root)
    required = set(_PLACEHOLDER.findall(template))
    supplied = set(values)
    missing = required.difference(supplied)
    extra = supplied.difference(required)
    if missing or extra:
        details = []
        if missing:
            details.append("missing: " + ", ".join(sorted(missing)))
        if extra:
            details.append("unknown: " + ", ".join(sorted(extra)))
        raise ValueError("invalid prompt variables (" + "; ".join(details) + ")")

    rendered = template
    for placeholder in sorted(required):
        value = values[placeholder]
        replacement = value if isinstance(value, str) else canonical_json(value)
        rendered = rendered.replace("{{" + placeholder + "}}", replacement)
    return rendered


def runtime_model_metadata(
    exposed: Mapping[str, Any] | None,
    *,
    config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Record exposed model metadata, using ``unavailable`` for unknowns.

    Requested model settings are intentionally not copied into runtime
    metadata.  Additional generation parameters exposed by a provider are kept
    beneath ``generation_parameters``.
    """

    loaded = config if config is not None else load_agent_config()
    defaults = loaded.get("model", {}).get("runtime_metadata_defaults")
    if not isinstance(defaults, Mapping):
        raise ValueError("model.runtime_metadata_defaults must be an object")
    result = dict(defaults)
    for key, value in (exposed or {}).items():
        if key not in result:
            raise ValueError(f"unknown runtime model metadata field: {key}")
        result[key] = "unavailable" if value is None or value == "" else value
    for key, value in tuple(result.items()):
        if value is None or value == "":
            result[key] = "unavailable"
    return result


__all__ = [
    "PromptIntegrityError",
    "PromptSpec",
    "canonical_json",
    "get_prompt_spec",
    "load_agent_config",
    "load_prompt",
    "prompt_manifest",
    "render_prompt",
    "repository_root",
    "runtime_model_metadata",
    "sha256_file",
    "verify_prompt_hashes",
]
