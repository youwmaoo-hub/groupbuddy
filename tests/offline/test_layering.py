"""分层边界（唯一权威说明：docs/architecture.md §2）：适配器唯一、配置唯一、领域层纯净。"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
CONFIG_PATH = APP / "config.py"
ASSEMBLY_ROOT = APP / "main.py"
ADAPTER_DIRS = {"telegram"}  # 适配器层目录：唯一允许 import 框架
FRAMEWORK_ROOTS = {"aiogram"}
DOMAIN_FORBIDDEN_ROOTS = {"aiogram", "openai", "aiosqlite"}
ENV_NAMES = {"environ", "getenv"}


def _sources() -> list[Path]:
    return sorted(APP.rglob("*.py"))


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imported_roots(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _app_imports(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module.startswith("app."):
                modules.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("app."):
                    modules.add(alias.name)
    return modules


def _env_access(tree: ast.AST) -> list[str]:
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ENV_NAMES:
            if isinstance(node.value, ast.Name) and node.value.id == "os":
                hits.append(f"os.{node.attr}")
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module == "os":
            hits.extend(alias.name for alias in node.names if alias.name in ENV_NAMES)
    return hits


class LayeringTests(unittest.TestCase):
    def test_framework_imports_stay_in_adapter_or_assembly_root(self) -> None:
        offenders: list[str] = []
        for path in _sources():
            if path == ASSEMBLY_ROOT or path.parent.name in ADAPTER_DIRS:
                continue
            hit = _imported_roots(_tree(path)) & FRAMEWORK_ROOTS
            if hit:
                offenders.append(f"{path.relative_to(APP.parent)} -> {sorted(hit)}")
        self.assertEqual([], offenders, "aiogram 只能出现在 app/telegram/ 与装配根 app/main.py")

    def test_environment_is_read_only_by_config(self) -> None:
        offenders: list[str] = []
        for path in _sources():
            if path == CONFIG_PATH:
                continue
            hits = _env_access(_tree(path))
            if hits:
                offenders.append(f"{path.relative_to(APP.parent)} -> {sorted(set(hits))}")
        self.assertEqual([], offenders, "只有 app/config.py 可以读环境变量")

    def test_domain_layer_has_no_outward_dependencies(self) -> None:
        offenders: list[str] = []
        for path in sorted((APP / "domain").rglob("*.py")):
            tree = _tree(path)
            foreign = _imported_roots(tree) & DOMAIN_FORBIDDEN_ROOTS
            cross = {name for name in _app_imports(tree) if not name.startswith("app.domain")}
            if foreign or cross:
                offenders.append(f"{path.relative_to(APP.parent)} -> {sorted(foreign | cross)}")
        self.assertEqual([], offenders, "app/domain/ 只依赖标准库与自身")


if __name__ == "__main__":
    unittest.main()
