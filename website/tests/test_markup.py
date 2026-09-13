import pytest

import markup


@pytest.fixture(scope="module")
def md():
    return markup.parser()


def html_of(md, text):
    return markup.render(md, markup.parse(md, text, "doc.md"))


@pytest.mark.parametrize(
    "text, slug",
    [
        ("Quick start", "quick-start"),
        ("The first run, measured twice", "the-first-run-measured-twice"),
        (
            "Why this is not another chat-with-an-AI app",
            "why-this-is-not-another-chat-with-an-ai-app",
        ),
        ("S2 — on a busy machine", "s2--on-a-busy-machine"),
        ("What’s measured?", "whats-measured"),
        ("Café au lait", "café-au-lait"),
        ("snake_case stays", "snake_case-stays"),
        (
            "0021 — Dependencies, images and the supply chain",
            "0021--dependencies-images-and-the-supply-chain",
        ),
    ],
)
def test_heading_ids_are_the_ones_github_makes(text, slug):
    assert markup.github_slug(text) == slug


def test_headings_are_collected_with_unique_ids(md):
    document = markup.parse(
        md, "# Title\n\n## Same\n\ntext\n\n## Same\n\n## The *first* `run`\n", "d.md"
    )

    assert [(h.level, h.id, h.text) for h in document.headings] == [
        (1, "title", "Title"),
        (2, "same", "Same"),
        (2, "same-1", "Same"),
        (2, "the-first-run", "The first run"),
    ]
    assert document.title == "Title"
    assert document.anchors == {"title", "same", "same-1", "the-first-run"}


def test_a_table_scrolls_inside_its_own_box(md):
    rendered = html_of(md, "| a | b |\n|---|---|\n| 1 | 2 |\n")

    assert rendered.startswith('<div class="table-wrap">\n<table>')
    assert rendered.rstrip().endswith("</table>\n</div>")


def test_a_mermaid_block_is_left_for_the_browser_to_draw(md):
    rendered = html_of(md, "```mermaid\ngraph LR\n  A --> B\n```\n")

    assert rendered == '<pre class="mermaid">graph LR\n  A --&gt; B\n</pre>\n'


def test_a_code_block_is_escaped_and_names_its_language(md):
    rendered = html_of(md, "```bash\necho <x> & done\n```\n")

    assert (
        rendered
        == '<pre><code class="language-bash">echo &lt;x&gt; &amp; done\n</code></pre>\n'
    )


def test_raw_html_outside_the_allowed_tags_is_reported_with_its_line(md):
    document = markup.parse(md, "Fine.\n\nText <script>alert(1)</script>\n", "doc.md")

    assert document.problems == [
        "doc.md:3: raw HTML <script> is not allowed",
        "doc.md:3: raw HTML <script> is not allowed",
    ]


def test_the_tags_the_documents_use_are_allowed(md):
    text = '<div align="center">\n\n# T\n\n</div>\n\n<sub>A caption, <i>quietly</i>.</sub>\n'

    assert markup.parse(md, text, "doc.md").problems == []


def test_a_tag_inside_code_is_text_not_html(md):
    document = markup.parse(
        md, "The class moved to `<html>`.\n\n```\n<script>\n```\n", "doc.md"
    )

    assert document.problems == []


def test_every_link_and_image_can_be_pointed_elsewhere(md):
    document = markup.parse(md, "See [a](a.md#x).\n\n![alt](pic.png)\n", "doc.md")

    found = list(markup.links(document))
    assert [(link.url, link.image, link.line) for link in found] == [
        ("a.md#x", False, 1),
        ("pic.png", True, 3),
    ]

    found[0].point_at("a.html#x")
    found[1].point_at("images/pic.png")
    rendered = markup.render(md, document)
    assert 'href="a.html#x"' in rendered
    assert 'src="images/pic.png"' in rendered


def test_the_summary_is_the_first_paragraph_as_plain_text(md):
    document = markup.parse(
        md, "# T\n\nThe **first** `para`\nwraps.\n\nThe second.\n", "d.md"
    )

    assert document.summary() == "The first para wraps."
    assert document.summary(limit=10) == "The first…"
