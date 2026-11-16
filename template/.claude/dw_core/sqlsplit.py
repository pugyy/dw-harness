"""Statement-level SQL text utilities shared by lint, guard and lineage.

The scanner understands: line comments (--, #), block comments, single /
double quoted strings, backtick and bracket identifiers, and semicolons that
separate statements. String bodies are blanked so keywords inside literals
(e.g. 'drop table x') can never match rules; newlines are preserved so
per-line and per-offset line numbers stay meaningful.
"""
from __future__ import annotations

import re
from typing import Iterator, List, NamedTuple, Tuple


class Statement(NamedTuple):
    index: int
    start_line: int  # 1-based line of first non-space char
    text: str  # original statement text
    code: str  # comments stripped, string bodies blanked, layout preserved


class ParseProblem(NamedTuple):
    line: int
    message: str


def scan_sql(sql: str) -> Tuple[List[Statement], List[ParseProblem]]:
    """Split *sql* into statements, tracking line numbers and problems."""
    statements: List[Statement] = []
    problems: List[ParseProblem] = []
    buf: List[Tuple[str, str]] = []  # (code_char, orig_char)
    stmt_first_line = None
    line = 1
    i = 0
    n = len(sql)
    state = "code"  # code | line_comment | block_comment | squote | dquote | backtick

    def note_real(ch: str) -> None:
        nonlocal stmt_first_line
        if stmt_first_line is None and not ch.isspace():
            stmt_first_line = line

    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""
        if state == "code":
            if ch == "-" and nxt == "-":
                state = "line_comment"
                buf.append((" ", " "))
                buf.append((" ", " "))
                i += 2
                continue
            if ch == "#":
                state = "line_comment"
                buf.append((" ", " "))
                i += 1
                continue
            if ch == "/" and nxt == "*":
                state = "block_comment"
                buf.append((" ", " "))
                buf.append((" ", " "))
                i += 2
                continue
            if ch == "'":
                state = "squote"
                note_real(ch)
                buf.append(("'", "'"))
                i += 1
                continue
            if ch == '"':
                state = "dquote"
                note_real(ch)
                buf.append(('"', '"'))
                i += 1
                continue
            if ch == "`":
                state = "backtick"
                note_real(ch)
                buf.append(("`", "`"))
                i += 1
                continue
            if ch == ";":
                _flush(buf, statements, stmt_first_line)
                buf = []
                stmt_first_line = None
                i += 1
                if ch == "\n":
                    line += 1
                continue
            note_real(ch)
            buf.append((ch, ch))
            if ch == "\n":
                line += 1
            i += 1
            continue
        if state == "line_comment":
            if ch == "\n":
                state = "code"
                buf.append(("\n", "\n"))
                line += 1
            else:
                buf.append((" ", " "))
            i += 1
            continue
        if state == "block_comment":
            if ch == "*" and nxt == "/":
                buf.append((" ", " "))
                buf.append((" ", " "))
                state = "code"
                i += 2
                continue
            buf.append(("\n" if ch == "\n" else " ", ch))
            if ch == "\n":
                line += 1
            i += 1
            continue
        quote = {"squote": "'", "dquote": '"', "backtick": "`"}[state]
        if ch == quote:
            if state == "squote" and nxt == "'":  # escaped ''
                buf.append((" ", " "))
                buf.append(("'", "'"))
                i += 2
                continue
            buf.append((quote, quote))
            state = "code"
            i += 1
            continue
        if ch == "\n" and state != "backtick":
            problems.append(ParseProblem(line, "unterminated string literal"))
            state = "code"
            buf.append(("\n", "\n"))
            line += 1
            i += 1
            continue
        buf.append((" " if ch != "\n" else "\n", ch))
        if ch == "\n":
            line += 1
        i += 1
        continue
    if state in ("squote", "dquote"):
        problems.append(ParseProblem(line, "unterminated string literal"))
    if state == "block_comment":
        problems.append(ParseProblem(line, "unterminated block comment"))
    _flush(buf, statements, stmt_first_line)
    return statements, problems


def _flush(buf: List[Tuple[str, str]], statements: List[Statement], first_line) -> None:
    if not buf:
        return
    text = "".join(orig for _, orig in buf)
    code = "".join(code_ch for code_ch, _ in buf)
    if not re.search(r"[A-Za-z0-9\u4e00-\u9fff]", text):
        return
    statements.append(Statement(len(statements), first_line or 1, text, code))


CLAUSE_ENDERS = {
    "from", "where", "group", "having", "order", "limit", "union",
    "minus", "except", "intersect", "on", "join", "lateral", "window",
}
_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def iter_select_clauses(code: str) -> Iterator[Tuple[int, int]]:
    """Yield (start, end) offsets of every SELECT's column list in *code*.

    Works at any parenthesis depth: each SELECT captures its own list, ended
    by the first clause keyword at the same depth (or end of text).
    """
    depth = 0
    i = 0
    n = len(code)
    while i < n:
        ch = code[i]
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        m = _WORD_RE.match(code, i)
        if m and m.group(0).lower() == "select":
            j = m.end()
            d = depth
            end = n
            while j < n:
                cj = code[j]
                if cj == "(":
                    d += 1
                elif cj == ")":
                    if d == depth:
                        end = j
                        break
                    d -= 1
                elif d == depth:
                    w = _WORD_RE.match(code, j)
                    if w and w.group(0).lower() in CLAUSE_ENDERS:
                        end = j
                        break
                    if cj == ";":
                        end = j
                        break
                j += 1
            yield (i, end)
            i = m.end()
            continue
        i += 1


def strip_comments(sql: str) -> str:
    stmts, _ = scan_sql(sql)
    return ";\n".join(s.code for s in stmts)
