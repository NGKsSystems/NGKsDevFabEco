from __future__ import annotations

from pathlib import Path


SOURCE_EXTENSION_TO_LANGUAGE = {
    ".c": "C",
    ".h": "C/C++ Header",
    ".cc": "C++",
    ".cpp": "C++",
    ".cxx": "C++",
    ".hpp": "C++",
    ".hh": "C++",
    ".hxx": "C++",
    ".ixx": "C++",
    ".cppm": "C++",
    ".cs": "C#",
    ".java": "Java",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".groovy": "Groovy",
    ".scala": "Scala",
    ".vb": "VB.NET",
    ".fs": "F#",
    ".fsi": "F#",
    ".fsscript": "F#",
    ".py": "Python",
    ".pyw": "Python",
    ".rs": "Rust",
    ".go": "Go",
    ".zig": "Zig",
    ".d": "D",
    ".nim": "Nim",
    ".adb": "Ada",
    ".ads": "Ada",
    ".asm": "Assembly",
    ".s": "Assembly",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".coffee": "CoffeeScript",
    ".elm": "Elm",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".php": "PHP",
    ".rb": "Ruby",
    ".ex": "Elixir",
    ".exs": "Elixir",
    ".erl": "Erlang",
    ".hrl": "Erlang",
    ".clj": "Clojure",
    ".cljs": "Clojure",
    ".cljc": "Clojure",
    ".hx": "Haxe",
    ".lua": "Lua",
    ".pl": "Perl",
    ".pm": "Perl",
    ".tcl": "Tcl",
    ".awk": "Awk",
    ".fish": "Fish",
    ".swift": "Swift",
    ".dart": "Dart",
    ".m": "Objective-C/MATLAB/Octave",
    ".mm": "Objective-C++",
    ".r": "R",
    ".jl": "Julia",
    ".matlab": "MATLAB",
    ".oct": "Octave",
    ".sas": "SAS",
    ".do": "Stata",
    ".mli": "OCaml",
    ".ml": "OCaml",
    ".re": "Reason/Rescript",
    ".rei": "Reason/Rescript",
    ".hs": "Haskell",
    ".lisp": "Common Lisp",
    ".lsp": "Common Lisp",
    ".scm": "Scheme",
    ".ss": "Scheme",
    ".pro": "Prolog",
    ".gd": "GDScript",
    ".sol": "Solidity",
    ".vala": "Vala",
    ".abap": "ABAP",
    ".cbl": "COBOL",
    ".cob": "COBOL",
    ".pas": "Delphi/Object Pascal",
    ".dpr": "Delphi/Object Pascal",
    ".cr": "Crystal",
    ".apex": "Apex",
    ".f": "Fortran",
    ".f90": "Fortran",
    ".f95": "Fortran",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".ps1": "PowerShell",
    ".bat": "Batch",
    ".cmd": "Batch",
}


def _classify_m_file(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")[:4096]
    except OSError:
        return "Objective-C/MATLAB/Octave"

    lowered = text.lower()
    if "@interface" in text or "@implementation" in text or "#import" in text:
        return "Objective-C"
    if "function " in lowered or "end" in lowered:
        return "MATLAB/Octave"
    return "Objective-C/MATLAB/Octave"


def detect_language_for_path(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext == ".m":
        return _classify_m_file(path)
    return SOURCE_EXTENSION_TO_LANGUAGE.get(ext)


def confidence(score: int, top_score: int) -> float:
    if top_score <= 0:
        return 0.0
    ratio = float(score) / float(top_score)
    return round(min(0.99, max(0.1, ratio)), 2)


def primary_project_type(language_scores: dict[str, int]) -> str:
    if not language_scores:
        return "unknown"
    primary = next(iter(language_scores.keys()))
    mapping = {
        "C": "cpp_app",
        "C++": "cpp_app",
        "Python": "python_package",
        "JavaScript": "node_app",
        "TypeScript": "node_app",
        "C#": "dotnet_app",
        "Java": "jvm_app",
        "Kotlin": "jvm_app",
    }
    return mapping.get(primary, "mixed")
