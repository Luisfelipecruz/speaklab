"""Markdown to HTML, as GitHub renders this repository's documents.

CommonMark with GitHub's tables and strikethrough; heading ids made the way GitHub makes
them, so a link to `#the-first-run-measured-twice` written against GitHub lands on the same
heading here; and raw HTML limited to the few tags the documents use. GitHub drops a tag
outside its own allowlist without a word; here one outside this list is reported, so a
document cannot read one way on GitHub and another on the site.

Links are not resolved here. `links` yields every link and image for the builder to point
somewhere, and `render` turns the tokens into HTML after it has.
"""

from __future__ import annotations

import html
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.anchors import anchors_plugin

ALLOWED_TAGS = frozenset(
    {"b", "br", "details", "div", "em", "i", "kbd", "strong", "sub", "summary", "sup"}
)
TAG = re.compile(r"</?([a-zA-Z][a-zA-Z0-9-]*)")


def github_slug(text: str) -> str:
    """The id GitHub gives a heading: lower case, punctuation dropped, each space a hyphen.

    Letters, digits and marks in any script survive, as do hyphens and underscores; an em
    dash between two spaces therefore leaves two hyphens, as it does on GitHub.
    """
    kept = []
    for character in text.strip().lower():
        if character == " ":
            kept.append("-")
        elif character == "-" or unicodedata.category(character)[0] in "LNM":
            kept.append(character)
        elif unicodedata.category(character) == "Pc":
            kept.append(character)
    return "".join(kept)


@dataclass(frozen=True)
class Heading:
    level: int
    id: str
    text: str


@dataclass
class Document:
    tokens: list[Token]
    headings: list[Heading]
    problems: list[str]

    @property
    def title(self) -> str | None:
        return next((h.text for h in self.headings if h.level == 1), None)

    @property
    def anchors(self) -> set[str]:
        return {h.id for h in self.headings}

    def summary(self, limit: int = 160) -> str:
        """The first paragraph as plain text, for a page's description."""
        for index, token in enumerate(self.tokens):
            if token.type == "paragraph_open" and index + 1 < len(self.tokens):
                text = " ".join(_plain(self.tokens[index + 1]).split())
                if text:
                    return (
                        text if len(text) <= limit else text[: limit - 1].rstrip() + "…"
                    )
        return ""


def _fence(self, tokens: list[Token], index: int, options, env) -> str:
    token = tokens[index]
    language = token.info.strip().split(maxsplit=1)[0] if token.info.strip() else ""
    code = html.escape(token.content)
    if language == "mermaid":
        # Drawn in the browser by site.js; until then, and without it, the source shows.
        return f'<pre class="mermaid">{code}</pre>\n'
    attribute = f' class="language-{html.escape(language)}"' if language else ""
    return f"<pre><code{attribute}>{code}</code></pre>\n"


def _table_open(self, tokens: list[Token], index: int, options, env) -> str:
    # Wide tables scroll inside their own box instead of widening the page.
    return '<div class="table-wrap">\n<table>\n'


def _table_close(self, tokens: list[Token], index: int, options, env) -> str:
    return "</table>\n</div>\n"


def parser() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
    md.use(
        anchors_plugin,
        min_level=1,
        max_level=6,
        slug_func=github_slug,
        permalink=True,
        permalinkSymbol="#",
    )
    md.add_render_rule("fence", _fence)
    md.add_render_rule("table_open", _table_open)
    md.add_render_rule("table_close", _table_close)
    return md


def _plain(inline: Token) -> str:
    parts = []
    for child in inline.children or []:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        elif child.type in ("softbreak", "hardbreak"):
            parts.append(" ")
    return "".join(parts)


def parse(md: MarkdownIt, text: str, name: str) -> Document:
    tokens = md.parse(text)
    headings: list[Heading] = []
    problems: list[str] = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            inline = tokens[index + 1]
            # Stripped, because the permalink the anchors plugin appends leaves a space.
            text_of = "".join(
                child.content
                for child in (inline.children or [])
                if child.type in ("text", "code_inline")
            ).strip()
            headings.append(
                Heading(int(token.tag[1]), str(token.attrGet("id")), text_of)
            )
        for raw in _raw_html(token):
            for tag in TAG.findall(raw.content):
                if tag.lower() not in ALLOWED_TAGS:
                    problems.append(
                        f"{name}:{_line(token)}: raw HTML <{tag}> is not allowed"
                    )
    return Document(tokens, headings, problems)


def _raw_html(token: Token) -> Iterator[Token]:
    if token.type == "html_block":
        yield token
    for child in token.children or []:
        if child.type == "html_inline":
            yield child


def _line(token: Token) -> int:
    return token.map[0] + 1 if token.map else 0


@dataclass(frozen=True)
class Link:
    token: Token
    attribute: str
    line: int

    @property
    def image(self) -> bool:
        return self.attribute == "src"

    @property
    def url(self) -> str:
        return str(self.token.attrGet(self.attribute) or "")

    def point_at(self, url: str) -> None:
        self.token.attrSet(self.attribute, url)


def links(document: Document) -> Iterator[Link]:
    for token in document.tokens:
        for child in token.children or []:
            if child.type == "link_open":
                yield Link(child, "href", _line(token))
            elif child.type == "image":
                yield Link(child, "src", _line(token))


def render(md: MarkdownIt, document: Document) -> str:
    return md.renderer.render(document.tokens, md.options, {})
