"""Module -> file -> item grouping."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, TypeVar

from ..config import Config
from ..parsers._util import normalize_path

T = TypeVar("T")

UNKNOWN_MODULE = "(unknown)"
ROOT_MODULE = "(root)"


@dataclass
class FileGroup:
    path: str
    items: list[Any] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModuleGroup:
    name: str
    files: list[FileGroup] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def items(self) -> list[Any]:
        return [i for f in self.files for i in f.items]


def module_of(path: str, config: Config) -> str:
    """Resolve the module name of a source file path.

    Order: explicit module_map (longest prefix) -> first `module_depth`
    directory components (after stripping source_root).
    """
    if not path:
        return UNKNOWN_MODULE
    p = normalize_path(path)

    best = ""
    for prefix in config.module_map:
        pre = normalize_path(prefix).rstrip("/")
        if (p == pre or p.startswith(pre + "/")) and len(pre) > len(best):
            best = pre
    if best:
        return config.module_map[next(k for k in config.module_map if normalize_path(k).rstrip("/") == best)]

    root = normalize_path(config.source_root).rstrip("/")
    if root and p.startswith(root + "/"):
        p = p[len(root) + 1:]

    dirs = p.split("/")[:-1]  # drop the file name
    dirs = dirs[: max(config.module_depth, 1)]
    return "/".join(dirs) if dirs else ROOT_MODULE


def group_by_module(
    items: Iterable[T],
    path_of: Callable[[T], str],
    config: Config,
) -> list[ModuleGroup]:
    """Group items into modules and files, both sorted by name."""
    tree: dict[str, dict[str, list[T]]] = defaultdict(lambda: defaultdict(list))
    for item in items:
        path = normalize_path(path_of(item)) if path_of(item) else ""
        tree[module_of(path, config)][path or UNKNOWN_MODULE].append(item)

    return [
        ModuleGroup(
            name=mod,
            files=[FileGroup(path=fp, items=its) for fp, its in sorted(files.items())],
        )
        for mod, files in sorted(tree.items())
    ]
