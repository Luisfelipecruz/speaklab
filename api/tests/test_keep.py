"""The keep check: what a version has to carry over from its source, by plain code."""

from services.keep import kept_items, missing, names_in

SOURCE = (
    "Laura, te escribo para avisarte que el informe de Acme se va a retrasar hasta el "
    "jueves 14. Son 1.250 dólares, a las 9:30, en https://acme.io/informe; escríbele a "
    "@omar o a luis.cruz@ejemplo.com."
)


def test_names_numbers_links_handles_and_addresses_are_what_must_be_kept():
    items = kept_items(SOURCE)

    assert items["names"] == ["Acme"]
    assert items["numbers"] == ["14", "1.250", "9:30"]
    assert items["links"] == ["https://acme.io/informe"]
    assert items["handles"] == ["@omar"]
    assert items["emails"] == ["luis.cruz@ejemplo.com"]


def test_a_name_that_opens_a_sentence_is_kept_once_it_is_known():
    assert "Laura" not in kept_items(SOURCE)["names"]
    assert "Laura" in kept_items(SOURCE, known=["Laura"])["names"]


def test_a_faithful_version_drops_nothing():
    version = (
        "Laura, I'm writing to let you know that Acme's report will be delayed until "
        "Thursday the 14th. It is $1,250, at 9:30, at https://acme.io/informe; write to "
        "@omar or luis.cruz@ejemplo.com."
    )
    assert missing(SOURCE, version, known=["Laura"]) == []


def test_what_a_version_dropped_is_named_as_it_was_written():
    version = "Laura, the report will be late. It is $1,250, at 9:00. Write to Omar."

    assert missing(SOURCE, version) == [
        "luis.cruz@ejemplo.com",
        "https://acme.io/informe",
        "@omar",
        "Acme",
        "14",
        "9:30",
    ]


def test_numbers_are_compared_by_their_digit_groups():
    assert missing("la factura 4821 por 1.250", "invoice 4821 for 1,250") == []
    assert missing("la factura 4821", "invoice 482") == ["4821"]
    assert missing("a las 9:30", "at 9.30") == []
    assert missing("el 300 555 2741", "300-555-2741") == []


def test_a_number_said_twice_has_to_be_there_twice():
    assert missing("2 cafés y 2 tés", "2 coffees and teas") == ["2"]


def test_a_name_inside_a_link_does_not_keep_the_name():
    assert missing("Habla con Acme", "Talk to them at acme.io") == ["Acme"]


def test_names_are_compared_without_case_or_accents():
    assert (
        missing("Ya llegué a Dubái, voy a México", "I'm in Dubai, going to Mexico")
        == []
    )


def test_english_capital_i_is_not_a_name():
    assert names_in("Hi Laura, I think I'm late and I'll call.") == ["Laura"]
