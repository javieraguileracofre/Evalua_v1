# tools/export_estructura.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Tuple


# =========================
# CONFIG
# =========================
DEFAULT_OUT = "estructura_proyecto.txt"

# Carpetas típicas a ignorar (puedes ajustar)
DEFAULT_EXCLUDE_DIRS = {
    ".git", ".idea", ".vscode", "__pycache__", ".pytest_cache", ".mypy_cache",
    "venv", ".venv", "env", ".env", "node_modules",
    "dist", "build", ".build", ".cache",
}

# Archivos típicos a ignorar (puedes ajustar)
DEFAULT_EXCLUDE_FILES = {
    ".DS_Store",
}

# Extensiones "pesadas" que normalmente no aportan al árbol
DEFAULT_EXCLUDE_EXTS = {
    ".pyc", ".pyo", ".pyd", ".log",
}


@dataclass(frozen=True)
class Options:
    root: Path
    out_file: Path
    exclude_dirs: set[str]
    exclude_files: set[str]
    exclude_exts: set[str]
    max_depth: Optional[int]
    include_meta: bool  # tamaño y mtime
    follow_symlinks: bool


def _human_bytes(n: int) -> str:
    # Formato simple sin dependencias
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(n)
    for u in units:
        if size < 1024.0 or u == units[-1]:
            if u == "B":
                return f"{int(size)} {u}"
            return f"{size:.1f} {u}"
        size /= 1024.0
    return f"{n} B"


def _is_excluded_dir(name: str, opt: Options) -> bool:
    return name in opt.exclude_dirs


def _is_excluded_file(path: Path, opt: Options) -> bool:
    if path.name in opt.exclude_files:
        return True
    if path.suffix.lower() in opt.exclude_exts:
        return True
    return False


def _safe_stat(path: Path) -> Tuple[Optional[int], Optional[float]]:
    try:
        st = path.stat()
        return st.st_size, st.st_mtime
    except Exception:
        return None, None


def _format_meta(path: Path) -> str:
    size, mtime = _safe_stat(path)
    parts: List[str] = []
    if size is not None:
        parts.append(_human_bytes(size))
    if mtime is not None:
        parts.append(datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M"))
    if parts:
        return "  [" + " | ".join(parts) + "]"
    return ""


def build_tree_lines(opt: Options) -> List[str]:
    root = opt.root.resolve()
    lines: List[str] = []

    header = [
        "Estructura del proyecto",
        f"Root: {root}",
        f"Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ]
    lines.extend(header)

    def walk_dir(current: Path, prefix: str, depth: int) -> None:
        if opt.max_depth is not None and depth > opt.max_depth:
            return

        try:
            entries = list(current.iterdir())
        except PermissionError:
            lines.append(prefix + "└── [SIN PERMISOS]")
            return
        except Exception:
            lines.append(prefix + "└── [ERROR LEYENDO]")
            return

        # Filtrar
        dirs = []
        files = []
        for e in entries:
            if e.is_dir() and (opt.follow_symlinks or not e.is_symlink()):
                if _is_excluded_dir(e.name, opt):
                    continue
                dirs.append(e)
            else:
                if _is_excluded_file(e, opt):
                    continue
                files.append(e)

        # Orden: dirs primero, luego archivos (alfabético)
        dirs.sort(key=lambda p: p.name.lower())
        files.sort(key=lambda p: p.name.lower())

        all_entries = dirs + files
        for i, e in enumerate(all_entries):
            is_last = (i == len(all_entries) - 1)
            branch = "└── " if is_last else "├── "
            next_prefix = prefix + ("    " if is_last else "│   ")

            name = e.name
            if e.is_dir():
                lines.append(prefix + branch + name + "/")
                walk_dir(e, next_prefix, depth + 1)
            else:
                meta = _format_meta(e) if opt.include_meta else ""
                lines.append(prefix + branch + name + meta)

    # Raíz
    lines.append(f"{opt.root.name}/")
    walk_dir(root, "", 1)

    return lines


def export_tree(
    root: str = ".",
    out_file: str = DEFAULT_OUT,
    max_depth: Optional[int] = None,
    include_meta: bool = False,
    follow_symlinks: bool = False,
    exclude_dirs: Optional[Iterable[str]] = None,
    exclude_files: Optional[Iterable[str]] = None,
    exclude_exts: Optional[Iterable[str]] = None,
) -> Path:
    opt = Options(
        root=Path(root),
        out_file=Path(out_file),
        exclude_dirs=set(exclude_dirs) if exclude_dirs else set(DEFAULT_EXCLUDE_DIRS),
        exclude_files=set(exclude_files) if exclude_files else set(DEFAULT_EXCLUDE_FILES),
        exclude_exts=set(exclude_exts) if exclude_exts else set(DEFAULT_EXCLUDE_EXTS),
        max_depth=max_depth,
        include_meta=include_meta,
        follow_symlinks=follow_symlinks,
    )

    lines = build_tree_lines(opt)
    opt.out_file.write_text("\n".join(lines), encoding="utf-8")
    return opt.out_file


if __name__ == "__main__":
    # Ejecuta desde la raíz:  python tools/export_estructura.py
    # Ajusta parámetros abajo si quieres:
    out = export_tree(
        root=".",
        out_file="estructura_proyecto.txt",
        max_depth=None,        # ej: 8 para cortar profundidad
        include_meta=False,    # True para incluir tamaño y fecha
        follow_symlinks=False,
    )
    print(f"OK -> {out.resolve()}")