"""Tokenization and lexical-anchor extraction from issue text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_BACKTICK = re.compile(r"`([^`\n]{1,200})`")
_DOTTED = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b")
_PYPATH = re.compile(r"[\w./-]+\.py\b")
_TRACE = re.compile(r'File "([^"]+)", line \d+, in (\w+)')
_URL = re.compile(r"https?://\S+")

STOP = set(
    """a an the and or but if then else of to in on for with without by from as at is are was were be been being
    this that these those it its we you i he she they them our your their not no yes do does did done can could
    should would will may might must have has had there here when where which who what why how all any some
    such than too very just also only into out up down over under again further once more most other same so
    pr fix fixes fixed issue issues add added adds adding update updated use used uses using support new now
    see https http github com www self cls none true false return def class import""".split()
)


def split_ident(tok: str) -> list[str]:
    parts: list[str] = []
    for p in tok.split("_"):
        if p:
            parts.extend(x for x in _CAMEL.split(p) if x)
    return [p.lower() for p in parts]


def tokenize(text: str) -> list[str]:
    """Lowercased sub-tokens (camel/snake split) + full identifiers, minus stopwords."""
    out: list[str] = []
    for w in _WORD.findall(text):
        subs = split_ident(w)
        if len(subs) > 1:
            out.append(w.lower())
        out.extend(subs)
    return [t for t in out if len(t) > 1 and t not in STOP and not t.isdigit()]


def name_tokens(name: str) -> list[str]:
    toks: list[str] = []
    for comp in name.split("."):
        toks.extend(split_ident(comp))
        toks.append(comp.lower())
    return [t for t in toks if len(t) > 1]


def _is_identifier_like(s: str) -> bool:
    return "_" in s or bool(_CAMEL.search(s)) or "." in s


@dataclass
class Anchors:
    backtick: set[str] = field(default_factory=set)  # identifiers that appeared inside `...`
    idents: set[str] = field(default_factory=set)  # identifier-like tokens anywhere (snake/Camel/dotted parts)
    dotted: set[str] = field(default_factory=set)  # a.b.c paths
    modules: set[str] = field(default_factory=set)  # dotted module paths from *.py file mentions
    trace_funcs: set[str] = field(default_factory=set)

    def all_last(self) -> set[str]:
        """Last components of every anchor (what we match against node short names)."""
        out = set(self.backtick) | set(self.idents) | set(self.trace_funcs)
        out |= {d.rsplit(".", 1)[-1] for d in self.dotted}
        return {a for a in out if a.lower() not in STOP and len(a) > 2}


def extract_anchors(text: str) -> Anchors:
    text = _URL.sub(" ", text)
    a = Anchors()
    for span in _BACKTICK.findall(text):
        for w in _WORD.findall(span):
            if w.lower() not in STOP and len(w) > 2:
                a.backtick.add(w)
        for d in _DOTTED.findall(span):
            a.dotted.add(d)
    for d in _DOTTED.findall(text):
        if not re.fullmatch(r"[\d.]+", d) and not d.endswith((".py", ".md", ".com", ".org")):
            a.dotted.add(d)
    for w in _WORD.findall(text):
        if _is_identifier_like(w) and len(w) > 3:
            a.idents.add(w)
    for p in _PYPATH.findall(text):
        mod = p.removesuffix(".py").strip("./").replace("/", ".")
        mod = mod.removeprefix("src.").removesuffix(".__init__")
        if mod:
            a.modules.add(mod)
    for f, fn in _TRACE.findall(text):
        a.trace_funcs.add(fn)
        mod = f.removesuffix(".py").replace("/", ".")
        a.modules.add(mod.rsplit("site-packages.", 1)[-1].removeprefix("src."))
    return a
