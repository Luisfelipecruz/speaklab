"""The split: what it does with a script, and what it refuses to do.

Pure arithmetic over strings, so these tests are the whole specification of it. The
property that matters most is the last one — the words come out as they went in. A split
that quietly dropped a sentence would be a rehearsal of a talk nobody is going to give,
and nothing downstream could notice: every count afterwards is against the section text.
"""

from services.sections import (
    sentence_spans,
    split_script,
    splittable,
    word_count,
)

MAX = 120
MIN = 8


def words(pieces: list[str]) -> list[str]:
    return " ".join(pieces).split()


def sentence(words_wanted: int, marker: str = "alpha") -> str:
    """One sentence of a known length, ending in a full stop."""
    return " ".join([marker] * (words_wanted - 1) + ["end."])


# ── Where it cuts ───────────────────────────────────────────────────────────


def test_a_blank_line_is_where_the_writer_said_a_part_ends():
    script = "The first part, short.\n\nThe second part, also short."
    assert split_script(script, MAX, 2) == [
        "The first part, short.",
        "The second part, also short.",
    ]


def test_wrapping_inside_a_paragraph_is_not_a_boundary():
    """A pasted script is wrapped text. Single newlines are the window, not the talk."""
    script = "One sentence that was\nwrapped by an editor."
    assert split_script(script, MAX, 2) == [
        "One sentence that was wrapped by an editor."
    ]


def test_a_paragraph_over_the_cap_is_cut_at_sentence_ends():
    script = " ".join(sentence(50) for _ in range(6))  # 300 words, six sentences

    pieces = split_script(script, MAX, MIN)

    assert len(pieces) == 3
    assert all(word_count(piece) <= MAX for piece in pieces)
    assert all(piece.endswith("end.") for piece in pieces)


def test_the_words_come_out_as_they_went_in():
    """The property everything else rests on: nothing added, dropped or reordered."""
    script = (
        "Good morning. I want to talk about three things.\n\n"
        + " ".join(sentence(40, marker="beta") for _ in range(8))
        + "\n\nThank you."
    )

    assert words(split_script(script, MAX, MIN)) == script.split()


def test_a_sentence_longer_than_the_cap_stays_whole():
    """There is nowhere to cut it that is not inside a sentence, so it is not cut.

    The alternative is a section that stops mid-clause, which is worse to rehearse than a
    long one and would be scored against half a thought.
    """
    script = " ".join(["alpha"] * 200) + "."

    pieces = split_script(script, MAX, MIN)

    assert len(pieces) == 1
    assert word_count(pieces[0]) == 200
    assert not splittable(pieces[0])


def test_a_short_tail_is_joined_to_the_piece_before_it():
    """Five words at the end are the end of a thought, not a thing to practise."""
    script = sentence(100) + " " + sentence(5)

    pieces = split_script(script, MAX, MIN)

    assert len(pieces) == 1
    assert word_count(pieces[0]) == 105


def test_a_short_tail_that_would_break_the_cap_stands_on_its_own():
    """A short section costs less than one too long to score in one go."""
    script = sentence(118) + " " + sentence(5)

    pieces = split_script(script, MAX, MIN)

    assert [word_count(piece) for piece in pieces] == [118, 5]


def test_an_empty_script_is_no_sections_rather_than_one_empty_one():
    assert split_script("", MAX, MIN) == []
    assert split_script("   \n\n  \n", MAX, MIN) == []


# ── Sentences ───────────────────────────────────────────────────────────────


def test_a_closing_quote_belongs_to_the_sentence_it_closes():
    text = 'He said "we shipped it." Then he sat down.'
    assert [text[a:b].strip() for a, b in sentence_spans(text)] == [
        'He said "we shipped it."',
        "Then he sat down.",
    ]


def test_text_with_no_sentence_mark_is_one_sentence():
    assert len(sentence_spans("three bullet points with no full stop")) == 1
    assert not splittable("three bullet points with no full stop")


def test_a_question_and_an_exclamation_end_sentences_too():
    text = "Why does it matter? It matters! Here is why."
    assert len(sentence_spans(text)) == 3
    assert splittable(text)
