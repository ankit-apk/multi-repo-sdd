from __future__ import annotations

import ast
import json
import re
from pathlib import Path

from multi_repo_sdd.models import ApiEndpoint, Capability, Dependency, Evidence, ModuleInfo
from multi_repo_sdd.safety import utc_now

PYTHON_ROUTE_DECORATORS = {
    "get": "GET",
    "post": "POST",
    "put": "PUT",
    "patch": "PATCH",
    "delete": "DELETE",
    "route": "ROUTE",
    "api_route": "ROUTE",
}

JS_ROUTE_RE = re.compile(
    r"""(?:app|router|server)\.(get|post|put|patch|delete|use)\(\s*['"]([^'"]+)['"]""",
    re.IGNORECASE,
)
JS_RAW_ROUTE_RE = re.compile(
    r"""req\.method\s*===\s*['"](GET|POST|PUT|PATCH|DELETE)['"]\s*&&\s*req\.url(?:\s*===\s*['"]([^'"]+)['"]|\s*&&\s*req\.url\.startsWith\(\s*['"]([^'"]+)['"])""",
    re.IGNORECASE,
)
HTTP_URL_RE = re.compile(r"""https?://[^\s'"]+|(?:localhost|127\.0\.0\.1):\d+[^\s'"]*""", re.IGNORECASE)
SERVICE_ENV_RE = re.compile(r"""([A-Z0-9_]+(?:URL|HOST|ENDPOINT))\s*[:=]\s*['"]?([^\s'"]+)""")
JAVA_MAPPING_RE = re.compile(
    r"""@(Get|Post|Put|Patch|Delete|Request)Mapping\s*\(\s*(?:value\s*=\s*)?["']([^"']+)["']""",
)
GO_HANDLE_RE = re.compile(
    r"""\.(?:HandleFunc|Handle|GET|POST|PUT|PATCH|DELETE)\(\s*["']([^"']+)["']"""
)
DOTNET_ROUTE_RE = re.compile(
    r"""\[Http(Get|Post|Put|Patch|Delete)\(\s*["']([^"']+)["']\s*\)\]""",
    re.IGNORECASE,
)
RULE_RE = re.compile(
    r"must not|cannot|not supported|only full|full-amount only|forbidden|idempoten|must be|not allowed|exceeds remaining",
    re.IGNORECASE,
)
CLIENT_RE = re.compile(
    r"urlopen|requests\.|httpx\.|fetch\(|axios\.|HttpClient|RestTemplate|http\.NewRequest|http\.Client"
)
QUEUE_RE = re.compile(r"\b(kafka|rabbitmq|amqp|sqs|nats|pubsub)\b", re.IGNORECASE)
EVENT_RE = re.compile(r"""\.(?:emit|publish|enqueue)\(\s*['"]([^'"]+)['"]""")
CODE_SUFFIXES = {".py", ".js", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".go", ".cs", ".kt"}
CONFIG_SUFFIXES = {".json", ".yml", ".yaml", ".toml", ".ini"}
SKIP_HOST_PARTS = ("w3.org", "json-schema", "schema.org", "github.com", "example.com", "githubusercontent.com")


def evidence(
    repo: str,
    description: str,
    file: str | None,
    symbol: str | None,
    sha: str | None,
    confidence: str,
    evidence_type: str = "source",
) -> Evidence:
    return Evidence(
        description=description,
        repository=repo,
        file=file,
        symbol=symbol,
        commit_sha=sha,
        timestamp=utc_now(),
        confidence=confidence,  # type: ignore[arg-type]
        evidence_type=evidence_type,
    )


def detect_stack(root: Path, files: list[Path]) -> tuple[str | None, list[str]]:
    names = {path.name.lower() for path in files}
    rels = {path.relative_to(root).as_posix() for path in files}
    frameworks: list[str] = []
    language = None
    if "pyproject.toml" in names or "requirements.txt" in names or "setup.py" in names:
        language = "python"
        text = _concat_named(root, ["pyproject.toml", "requirements.txt"])
        if "fastapi" in text.lower():
            frameworks.append("FastAPI")
        if "flask" in text.lower():
            frameworks.append("Flask")
        if "django" in text.lower():
            frameworks.append("Django")
    if "package.json" in names:
        language = language or "javascript"
        pkg = _read_json(root / "package.json")
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        if "express" in deps:
            frameworks.append("Express")
        if "fastify" in deps:
            frameworks.append("Fastify")
        if "next" in deps:
            frameworks.append("Next.js")
        if any(name.endswith(".ts") or name.endswith(".tsx") for name in rels):
            language = "typescript"
    if "pom.xml" in names or "build.gradle" in names or "build.gradle.kts" in names:
        language = language or "java"
        text = _concat_named(root, ["pom.xml", "build.gradle", "build.gradle.kts"])
        if "spring" in text.lower():
            frameworks.append("Spring")
    if "go.mod" in names:
        language = language or "go"
        frameworks.append("Go")
    if "Cargo.toml" in names:
        language = language or "rust"
    if any(name.endswith(".csproj") for name in names) or any(name.endswith(".cs") for name in rels):
        language = language or "dotnet"
    frameworks.extend(_sniff_frameworks(files))
    # Preserve order while dropping duplicates.
    unique: list[str] = []
    for item in frameworks:
        if item not in unique:
            unique.append(item)
    return language, unique


def discover_modules(root: Path, files: list[Path]) -> list[ModuleInfo]:
    modules: list[ModuleInfo] = []
    for candidate in ["src", "app", "lib", "pkg", "cmd", "internal", "services"]:
        path = root / candidate
        if path.is_dir():
            modules.append(ModuleInfo(name=candidate, path=candidate, description=f"Top-level {candidate} directory"))
    for path in files:
        rel = path.relative_to(root).as_posix()
        if rel.endswith("__init__.py") and path.parent != root:
            name = path.parent.relative_to(root).as_posix()
            if name not in {item.name for item in modules}:
                modules.append(ModuleInfo(name=name, path=name))
    return modules[:40]


def discover_python(root: Path, files: list[Path], repo: str, sha: str | None) -> tuple[list[ApiEndpoint], list[str], list[str]]:
    apis: list[ApiEndpoint] = []
    entry_points: list[str] = []
    symbols: list[str] = []
    for path in files:
        if path.suffix != ".py":
            continue
        source = _safe_read(path)
        if not source:
            continue
        rel = path.relative_to(root).as_posix()
        if path.name in {"main.py", "app.py", "wsgi.py", "asgi.py", "manage.py"}:
            entry_points.append(rel)
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                symbols.append(f"{rel}:{node.name}")
                route = _python_route(node)
                if route:
                    method, url = route
                    apis.append(
                        ApiEndpoint(
                            method=method,
                            path=url,
                            handler=node.name,
                            evidence=[
                                evidence(
                                    repo,
                                    f"{method} {url} handled by {node.name}",
                                    rel,
                                    node.name,
                                    sha,
                                    "verified",
                                    "api",
                                )
                            ],
                        )
                    )
    return apis, entry_points, symbols[:80]


def discover_javascript(root: Path, files: list[Path], repo: str, sha: str | None) -> tuple[list[ApiEndpoint], list[str]]:
    apis: list[ApiEndpoint] = []
    entry_points: list[str] = []
    pkg = _read_json(root / "package.json")
    scripts = pkg.get("scripts") if isinstance(pkg, dict) else {}
    if isinstance(scripts, dict) and "start" in scripts:
        entry_points.append("package.json:scripts.start")
    for path in files:
        if path.suffix not in {".js", ".ts", ".mjs", ".cjs"}:
            continue
        source = _safe_read(path)
        if not source:
            continue
        rel = path.relative_to(root).as_posix()
        if path.name in {"index.js", "index.ts", "server.js", "app.js", "main.ts"}:
            entry_points.append(rel)
        for match in JS_ROUTE_RE.finditer(source):
            method, url = match.group(1).upper(), match.group(2)
            apis.append(
                ApiEndpoint(
                    method=method,
                    path=url,
                    evidence=[
                        evidence(repo, f"{method} {url}", rel, None, sha, "verified", "api")
                    ],
                )
            )
        for match in JS_RAW_ROUTE_RE.finditer(source):
            method = match.group(1).upper()
            url = match.group(2) or match.group(3)
            apis.append(
                ApiEndpoint(
                    method=method,
                    path=url,
                    evidence=[
                        evidence(repo, f"{method} {url}", rel, None, sha, "verified", "api")
                    ],
                )
            )
    return apis, entry_points


def discover_java(root: Path, files: list[Path], repo: str, sha: str | None) -> list[ApiEndpoint]:
    apis: list[ApiEndpoint] = []
    for path in files:
        if path.suffix != ".java":
            continue
        source = _safe_read(path)
        rel = path.relative_to(root).as_posix()
        for match in JAVA_MAPPING_RE.finditer(source):
            verb = match.group(1).upper()
            method = "GET" if verb in {"GET", "REQUEST"} else verb
            apis.append(
                ApiEndpoint(
                    method=method,
                    path=match.group(2),
                    evidence=[evidence(repo, f"{method} {match.group(2)}", rel, None, sha, "verified", "api")],
                )
            )
    return apis


def discover_dotnet(root: Path, files: list[Path], repo: str, sha: str | None) -> list[ApiEndpoint]:
    apis: list[ApiEndpoint] = []
    for path in files:
        if path.suffix != ".cs":
            continue
        source = _safe_read(path)
        rel = path.relative_to(root).as_posix()
        for match in DOTNET_ROUTE_RE.finditer(source):
            method = match.group(1).upper()
            apis.append(
                ApiEndpoint(
                    method=method,
                    path=match.group(2),
                    evidence=[evidence(repo, f"{method} {match.group(2)}", rel, None, sha, "verified", "api")],
                )
            )
    return apis


def discover_go(root: Path, files: list[Path], repo: str, sha: str | None) -> list[ApiEndpoint]:
    apis: list[ApiEndpoint] = []
    for path in files:
        if path.suffix != ".go":
            continue
        source = _safe_read(path)
        rel = path.relative_to(root).as_posix()
        for match in GO_HANDLE_RE.finditer(source):
            apis.append(
                ApiEndpoint(
                    method="ROUTE",
                    path=match.group(1),
                    evidence=[evidence(repo, f"route {match.group(1)}", rel, None, sha, "verified", "api")],
                )
            )
    return apis


def discover_dependencies(
    root: Path,
    files: list[Path],
    repo: str,
    sha: str | None,
    registry_names: list[str],
) -> list[Dependency]:
    """Find relationships that code or configuration actually references.

    A repository name appearing only in prose does not create an edge.
    """
    found: dict[tuple[str, str, str], Dependency] = {}
    for path in files:
        rel = path.relative_to(root).as_posix()
        if path.name.lower().startswith("readme"):
            continue
        suffix = path.suffix.lower()
        is_code = suffix in CODE_SUFFIXES
        is_config = suffix in CONFIG_SUFFIXES or path.name == ".env"
        if not is_code and not is_config:
            continue
        source = _safe_read(path)
        if not source:
            continue
        is_test = _is_test_path(rel)
        _dependencies_in_file(
            found,
            source,
            rel,
            path,
            repo,
            sha,
            registry_names,
            is_code=is_code,
            is_test=is_test,
        )
    _shared_libraries(root, repo, sha, registry_names, found)
    return list(found.values())


def discover_business_rules(files: list[Path], root: Path) -> list[str]:
    rules: list[str] = []
    for path in files:
        if path.suffix.lower() not in {".py", ".js", ".ts", ".java", ".go", ".cs", ".md"}:
            continue
        text = _safe_read(path)
        if not text:
            continue
        rel = path.relative_to(root).as_posix()
        for index, line in enumerate(text.splitlines(), start=1):
            if not RULE_RE.search(line):
                continue
            stripped = line.strip()
            if len(stripped) < 8 or stripped.startswith(("import ", "from ")):
                continue
            rules.append(f"{rel}:{index}: {stripped[:180]}")
            if len(rules) >= 20:
                return rules
    return rules


def discover_capabilities(apis: list[ApiEndpoint], repo: str, sha: str | None) -> list[Capability]:
    capabilities: list[Capability] = []
    for api in apis:
        name = _capability_name(api.method, api.path)
        capabilities.append(
            Capability(
                name=name,
                description=f"{api.method} {api.path}",
                evidence=api.evidence
                or [evidence(repo, name, None, api.handler, sha, "inferred", "api")],
            )
        )
    if not capabilities:
        capabilities.append(
            Capability(
                name="undocumented-service",
                description="No HTTP API surface was detected. Purpose remains unknown.",
                evidence=[evidence(repo, "No API routes found", None, None, sha, "unknown", "absence")],
            )
        )
    return capabilities


def discover_database_notes(files: list[Path], root: Path) -> list[str]:
    notes: list[str] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        lowered = rel.lower()
        if "migration" in lowered or path.suffix in {".sql", ".prisma"}:
            notes.append(f"Schema or migration artifact at {rel}")
        if path.name in {"schema.prisma", "models.py", "models.ts"}:
            notes.append(f"Likely data model definition at {rel}")
    if not any("Schema or migration" in note or "data model" in note for note in notes):
        for path in files:
            if path.suffix.lower() not in {".py", ".js", ".ts"}:
                continue
            text = _safe_read(path)
            rel = path.relative_to(root).as_posix()
            if re.search(r"new\s+Map\s*\(|:\s*dict\[", text):
                notes.append(
                    f"Inferred: in-memory state in `{rel}`. No durable schema file was found."
                )
                break
    return notes[:30]


def discover_tests(files: list[Path], root: Path) -> list[str]:
    tests: list[str] = []
    for path in files:
        rel = path.relative_to(root).as_posix()
        name = path.name.lower()
        if (
            name.startswith("test_")
            or name.endswith(".test.js")
            or name.endswith(".spec.ts")
            or "/tests/" in f"/{rel}/"
            or "/test/" in f"/{rel}/"
        ):
            tests.append(rel)
    return tests[:50]


def _capability_name(method: str, path: str) -> str:
    parts = [segment for segment in path.split("/") if segment and not segment.startswith("{") and not segment.startswith(":")]
    stem = "-".join(parts) or "root"
    return f"{method.lower()}-{stem}"


def _python_route(node: ast.FunctionDef) -> tuple[str, str] | None:
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Attribute):
            method = PYTHON_ROUTE_DECORATORS.get(decorator.func.attr.lower())
            if method and decorator.args and isinstance(decorator.args[0], ast.Constant):
                value = decorator.args[0].value
                if isinstance(value, str):
                    return method, value
        if isinstance(decorator, ast.Call) and isinstance(decorator.func, ast.Name):
            method = PYTHON_ROUTE_DECORATORS.get(decorator.func.id.lower())
            if method and decorator.args and isinstance(decorator.args[0], ast.Constant):
                value = decorator.args[0].value
                if isinstance(value, str):
                    return method, value
    return None


def _match_registry(text: str, names: list[str], current: str) -> str | None:
    lowered = text.lower().replace("_", "-")
    for name in names:
        if name == current:
            continue
        token = re.escape(name.lower())
        if re.search(rf"(^|[^a-z0-9]){token}([^a-z0-9]|$)", lowered):
            return name
    return None


def _dependencies_in_file(
    found: dict[tuple[str, str, str], Dependency],
    source: str,
    rel: str,
    path: Path,
    repo: str,
    sha: str | None,
    registry_names: list[str],
    is_code: bool,
    is_test: bool,
) -> None:
    for env_name, value in SERVICE_ENV_RE.findall(source):
        blob = f"{env_name} {value}"
        target = _match_registry(blob, registry_names, repo)
        if target:
            _add_dependency(
                found,
                repo,
                target,
                "synchronous-api",
                env_name,
                "verified" if is_code and not is_test else "inferred",
                sha,
                evidence(
                    repo,
                    f"Configuration {env_name} references {target}",
                    rel,
                    env_name,
                    sha,
                    "verified" if is_code and not is_test else "inferred",
                    "config",
                ),
            )
            continue
        host = _host_from_url(value)
        if host and not _skipped_host(host):
            _add_dependency(
                found,
                repo,
                host,
                "external-service",
                env_name,
                "inferred",
                sha,
                evidence(repo, f"Configuration {env_name} points at external host {host}", rel, env_name, sha, "inferred", "config"),
            )
    for match in HTTP_URL_RE.finditer(source):
        url = match.group(0).rstrip(").,;")
        target = _match_registry(url, registry_names, repo)
        if not target:
            continue
        confidence = "inferred" if is_test or not is_code else "verified"
        symbol = _python_symbol_at(source, match.start()) if path.suffix == ".py" else None
        _add_dependency(
            found,
            repo,
            target,
            "synchronous-api",
            url,
            confidence,
            sha,
            evidence(repo, f"HTTP reference {url}", rel, symbol, sha, confidence, "source" if is_code else "config"),
        )
    if not is_code:
        return
    for name in registry_names:
        if name == repo or not re.search(rf"(^|[^A-Za-z0-9_.-]){re.escape(name)}([^A-Za-z0-9_.-]|$)", source):
            continue
        if QUEUE_RE.search(source):
            _add_dependency(
                found,
                repo,
                name,
                "message-queue",
                None,
                "inferred",
                sha,
                evidence(repo, f"Broker client and {name} appear in the same file", rel, None, sha, "inferred", "source"),
            )
        for event_name in EVENT_RE.findall(source):
            if name not in event_name and _match_registry(event_name, [name], repo) is None:
                continue
            _add_dependency(
                found,
                repo,
                name,
                "asynchronous-event",
                event_name,
                "inferred",
                sha,
                evidence(repo, f"Event {event_name} names {name}", rel, None, sha, "inferred", "source"),
            )


def _shared_libraries(
    root: Path,
    repo: str,
    sha: str | None,
    registry_names: list[str],
    found: dict[tuple[str, str, str], Dependency],
) -> None:
    pkg = _read_json(root / "package.json")
    declared = set()
    if isinstance(pkg, dict):
        declared.update((pkg.get("dependencies") or {}).keys())
        declared.update((pkg.get("devDependencies") or {}).keys())
    requirements = root / "requirements.txt"
    if requirements.is_file():
        for line in _safe_read(requirements).splitlines():
            package = re.split(r"[<>=\[]", line.strip(), maxsplit=1)[0].strip()
            if package:
                declared.add(package)
    for name in registry_names:
        if name == repo or name not in declared:
            continue
        _add_dependency(
            found,
            repo,
            name,
            "shared-library",
            name,
            "verified",
            sha,
            evidence(repo, f"Package manifest depends on {name}", "package manifest", name, sha, "verified", "config"),
        )


def _add_dependency(
    found: dict[tuple[str, str, str], Dependency],
    source: str,
    target: str,
    relation: str,
    interface: str | None,
    confidence: str,
    sha: str | None,
    item: Evidence,
) -> None:
    key = (source, target, relation)
    existing = found.get(key)
    if existing is None:
        found[key] = Dependency(
            source=source,
            target=target,
            type=relation,  # type: ignore[arg-type]
            interface=interface,
            confidence=confidence,  # type: ignore[arg-type]
            last_verified_commit=sha,
            evidence=[item],
        )
        return
    existing.evidence.append(item)
    if confidence == "verified":
        existing.confidence = "verified"
        existing.last_verified_commit = sha
    if interface and not existing.interface:
        existing.interface = interface


def _host_from_url(value: str) -> str | None:
    match = re.search(r"https?://([^/:]+)", value)
    if not match:
        return None
    return match.group(1)


def _skipped_host(host: str) -> bool:
    lowered = host.lower()
    return any(part in lowered for part in SKIP_HOST_PARTS)


def _is_test_path(rel: str) -> bool:
    name = Path(rel).name.lower()
    return (
        name.startswith("test_")
        or name.endswith(".test.js")
        or name.endswith(".spec.ts")
        or "/tests/" in f"/{rel}/"
        or "/test/" in f"/{rel}/"
    )


def _python_symbol_at(source: str, index: int) -> str | None:
    line = source.count("\n", 0, index) + 1
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    best: ast.AST | None = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            end = getattr(node, "end_lineno", node.lineno)
            if node.lineno <= line <= end and (best is None or node.lineno >= best.lineno):
                best = node
    if isinstance(best, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return best.name
    return None


def _sniff_frameworks(files: list[Path]) -> list[str]:
    found: list[str] = []
    checked = 0
    for path in files:
        if path.suffix.lower() not in {".py", ".js", ".ts", ".java", ".cs"}:
            continue
        text = _safe_read(path)[:20000]
        if not text:
            continue
        checked += 1
        lowered = text.lower()
        if "from fastapi" in lowered or "import fastapi" in lowered:
            found.append("FastAPI")
        if "from flask" in lowered or "import flask" in lowered:
            found.append("Flask")
        if 'require("http")' in text or "require('http')" in text:
            found.append("Node.js http")
        if path.suffix == ".java" and "springframework" in lowered:
            found.append("Spring")
        if checked >= 80:
            break
    return found


def _safe_read(path: Path) -> str:
    try:
        data = path.read_bytes()[:150_000]
    except OSError:
        return ""
    if b"\0" in data[:1024]:
        return ""
    return data.decode("utf-8", errors="replace")


def _concat_named(root: Path, names: list[str]) -> str:
    chunks: list[str] = []
    for name in names:
        path = root / name
        if path.is_file():
            chunks.append(_safe_read(path))
    return "\n".join(chunks)


def _read_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
