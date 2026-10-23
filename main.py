from __future__ import annotations

import ast
import shutil
import tempfile
import uuid
import zipfile
from collections import defaultdict, deque
from pathlib import Path, PurePosixPath
from typing import Any

import networkx as nx
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
STATIC_DIR = ROOT / "app" / "static"
MAX_ZIP_BYTES = 10 * 1024 * 1024
MAX_PY_FILES = 500
PROJECTS: dict[str, dict[str, Any]] = {}

app = FastAPI(title="CodeRipple", version="1.0.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def home():
    return FileResponse(STATIC_DIR / "index.html")


def safe_extract_python_files(zip_path: Path, destination: Path) -> list[Path]:
    """Extract only safe, reasonably sized Python files from a ZIP archive."""
    extracted: list[Path] = []
    with zipfile.ZipFile(zip_path) as archive:
        members = [m for m in archive.infolist() if not m.is_dir()]
        if len(members) > 3000:
            raise HTTPException(400, "ZIP contains too many entries (maximum 3000).")
        for member in members:
            posix = PurePosixPath(member.filename)
            if posix.is_absolute() or ".." in posix.parts:
                continue
            if not member.filename.lower().endswith(".py"):
                continue
            if member.file_size > 2 * 1024 * 1024:
                continue
            if len(extracted) >= MAX_PY_FILES:
                break
            target = destination.joinpath(*posix.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst)
            extracted.append(target)
    if not extracted:
        raise HTTPException(400, "No Python (.py) files were found in this ZIP.")
    return extracted


def module_name(relative_path: str) -> str:
    path = PurePosixPath(relative_path)
    parts = list(path.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = path.stem
    return ".".join(parts)


def analyse_project(project_dir: Path, files: list[Path]) -> dict[str, Any]:
    graph = nx.DiGraph()
    parsed: dict[str, ast.AST] = {}
    file_to_module: dict[str, str] = {}
    module_to_file: dict[str, str] = {}
    definitions: dict[str, set[str]] = defaultdict(set)
    imports: dict[str, set[str]] = defaultdict(set)
    calls: dict[str, set[str]] = defaultdict(set)
    line_info: dict[str, dict[str, int]] = defaultdict(dict)

    for path in files:
        rel = path.relative_to(project_dir).as_posix()
        mod = module_name(rel)
        file_to_module[rel] = mod
        module_to_file[mod] = rel
        graph.add_node(rel)
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=rel)
        except (SyntaxError, UnicodeDecodeError):
            continue
        parsed[rel] = tree

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                definitions[node.name].add(rel)
                line_info[rel][node.name] = getattr(node, "lineno", 1)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    imports[rel].add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports[rel].add(node.module)
                    for alias in node.names:
                        imports[rel].add(f"{node.module}.{alias.name}")
            elif isinstance(node, ast.Call):
                name = None
                if isinstance(node.func, ast.Name):
                    name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    name = node.func.attr
                if name:
                    calls[rel].add(name)

    # Import-based edges: source file -> imported project file.
    for rel in graph.nodes:
        mod = file_to_module[rel]
        for imported in imports[rel]:
            candidates = [imported, imported.split(".")[0]]
            for candidate in candidates:
                target = module_to_file.get(candidate)
                if target and target != rel:
                    graph.add_edge(rel, target, reason="imports", evidence=imported)
                    break

    # Function-call edges are approximate: same-named definitions can be ambiguous.
    for rel in graph.nodes:
        for call in calls[rel]:
            targets = definitions.get(call, set())
            for target in targets:
                if target != rel:
                    if graph.has_edge(rel, target):
                        old = graph[rel][target]
                        old["reason"] = "imports + calls"
                        old["evidence"] = f'{old.get("evidence", "")}, call {call}'.strip(", ")
                    else:
                        graph.add_edge(rel, target, reason="calls function", evidence=call)

    nodes = []
    for rel in sorted(graph.nodes):
        nodes.append({
            "id": rel,
            "module": file_to_module.get(rel, ""),
            "functions": sorted(definitions.keys()) if False else sorted(
                name for name, locations in definitions.items() if rel in locations
            ),
            "lines": len((project_dir / rel).read_text(encoding="utf-8", errors="ignore").splitlines())
        })
    edges = [
        {"source": source, "target": target, "reason": data.get("reason", "dependency"),
         "evidence": data.get("evidence", "")}
        for source, target, data in graph.edges(data=True)
    ]
    return {"graph": graph, "nodes": nodes, "edges": edges, "line_info": dict(line_info)}


def impact_report(project: dict[str, Any], changed_file: str) -> dict[str, Any]:
    graph: nx.DiGraph = project["graph"]
    if changed_file not in graph:
        raise HTTPException(404, "Selected file was not found in the analysed project.")

    # Edges point from a caller/importer to its dependency. A change to a target
    # may affect all files that can reach it, so traverse the reverse graph.
    reverse_graph = graph.reverse(copy=False)
    impacted = nx.single_source_shortest_path_length(reverse_graph, changed_file)
    impacted.pop(changed_file, None)
    node_map = {node["id"]: node for node in project["nodes"]}
    edge_map = {(e["source"], e["target"]): e for e in project["edges"]}

    results = []
    for filename, distance in sorted(impacted.items(), key=lambda item: (item[1], item[0])):
        reasons = []
        for predecessor in reverse_graph.predecessors(filename):
            if predecessor == changed_file or predecessor in impacted:
                edge = edge_map.get((predecessor, filename))
                if edge:
                    reasons.append({
                        "from": predecessor, "reason": edge["reason"],
                        "evidence": edge["evidence"]
                    })
        results.append({
            "file": filename,
            "distance": distance,
            "risk": "High" if distance == 1 else ("Medium" if distance == 2 else "Low"),
            "functions": node_map.get(filename, {}).get("functions", []),
            "reasons": reasons[:4]
        })

    return {
        "changed_file": changed_file,
        "impact_count": len(results),
        "results": results,
        "note": "Impact is an estimate based on static imports and function names. It is not a guarantee that a file will break."
    }


@app.post("/api/analyse")
async def analyse(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(400, "Please upload a .zip file containing a Python project.")
    raw = await file.read(MAX_ZIP_BYTES + 1)
    if len(raw) > MAX_ZIP_BYTES:
        raise HTTPException(413, "ZIP file is too large. Maximum size is 10 MB.")
    project_id = str(uuid.uuid4())
    work_dir = Path(tempfile.mkdtemp(prefix="coderipple_"))
    zip_path = work_dir / "upload.zip"
    zip_path.write_bytes(raw)
    source_dir = work_dir / "source"
    source_dir.mkdir()
    try:
        files = safe_extract_python_files(zip_path, source_dir)
        project = analyse_project(source_dir, files)
        PROJECTS[project_id] = {
            **project, "directory": str(source_dir), "work_dir": str(work_dir)
        }
        return {
            "project_id": project_id,
            "files": project["nodes"],
            "edges": project["edges"],
            "file_count": len(project["nodes"]),
            "edge_count": len(project["edges"])
        }
    except zipfile.BadZipFile:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(400, "That file is not a valid ZIP archive.")
    except Exception:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise


@app.post("/api/impact")
def get_impact(project_id: str = Form(...), changed_file: str = Form(...)):
    project = PROJECTS.get(project_id)
    if not project:
        raise HTTPException(404, "Project session expired. Please upload the ZIP again.")
    return impact_report(project, changed_file)


@app.get("/api/sample")
def download_sample():
    sample_dir = ROOT / "sample_project"
    from io import BytesIO
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(sample_dir.rglob("*.py")):
            archive.write(path, path.relative_to(sample_dir).as_posix())
    from fastapi.responses import StreamingResponse
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/zip",
                             headers={"Content-Disposition": 'attachment; filename="coderipple_sample.zip"'})

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "CodeRipple"}
