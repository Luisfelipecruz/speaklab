"""Rewrites of labelled answers, each marked as faithful or as adding a fact.

The answer drill asks a language model for the speaker's own answer said in fewer
sentences, and shows it only if a check finds nothing added that the speaker never said. A
rewrite that invents a number, a name or a cause puts words in the speaker's mouth and
teaches them to say things they do not know, so the check is measured against rewrites
written to do each thing.

A **faithful** rewrite keeps the speaker's points, facts and most of their words, joins
sentences and drops repeats — the rewrite the prompt asks for. One that **adds a fact**
brings in something the answer does not contain: a figure, a product, a person, a cause.
Each rewrite here was written before the check that scores it. `DEVELOPMENT` chose the
limit on invented words; `HELD_OUT` scores the check at that limit.

**The bar, set before the held-out rewrites were scored.** The check is kept only if, on
`HELD_OUT`, it withholds at least five of the six rewrites that add a fact and lets
through at least five of the six faithful ones.
"""

from __future__ import annotations

from dataclasses import dataclass

from tests.answer_labels import DEVELOPMENT as ANSWERS_DEVELOPMENT
from tests.answer_labels import HELD_OUT as ANSWERS_HELD_OUT


@dataclass(frozen=True)
class Rewrite:
    prompt: str
    answer: str
    rewrite: str
    adds_a_fact: bool


def _dev(index: int, rewrite: str, adds: bool) -> Rewrite:
    answer = ANSWERS_DEVELOPMENT[index]
    return Rewrite(answer.prompt, answer.transcript, rewrite, adds)


def _held(index: int, rewrite: str, adds: bool) -> Rewrite:
    answer = ANSWERS_HELD_OUT[index]
    return Rewrite(answer.prompt, answer.transcript, rewrite, adds)


DEVELOPMENT: list[Rewrite] = [
    _dev(
        0,
        "The new checkout broke payments for an hour, because the new version expected a "
        "field the old mobile app does not send. We didn't see it in testing, because our "
        "test data only had web orders. First we thought it was the payment provider, then "
        "the logs showed the error and we rolled back. In short, a missing field and a gap "
        "in our test data.",
        False,
    ),
    _dev(
        0,
        "The new checkout broke payments for an hour and cost us about 2000 orders, "
        "because the new version expected a field the old Android app does not send. We "
        "rolled back after the logs showed the error.",
        True,
    ),
    _dev(
        2,
        "We delivered the export two weeks late for two reasons: the client changed the "
        "file format in the middle of the project, and one developer was sick for a week. "
        "We warned the client about the risk but did not give them a new date early "
        "enough, which is why they were surprised. The delay was partly outside our "
        "control, but we should have communicated better.",
        False,
    ),
    _dev(
        2,
        "We delivered the export two weeks late because the client changed the file "
        "format and our lead developer resigned. We also underestimated the testing "
        "effort. We should have told them sooner.",
        True,
    ),
    _dev(
        6,
        "I chose Postgres for three reasons: our data is relational, we need transactions "
        "so a payment and an invoice are saved together, and the team already knows SQL. "
        "MongoDB is good for documents with a flexible shape, but we don't have that "
        "problem, so Postgres is the safer choice.",
        False,
    ),
    _dev(
        6,
        "I chose Postgres because our data is relational, it is cheaper to host on AWS, and "
        "it handled ten times more writes than MongoDB in our benchmarks. So Postgres is the "
        "safer choice.",
        True,
    ),
    _dev(
        8,
        "I think the feature should wait for the next sprint. We already promised eight "
        "stories and the team is at full capacity, so adding it would make the security "
        "fixes slip, and they are due before the audit. I can start the design this week, "
        "so the client gets it in three weeks.",
        False,
    ),
    _dev(
        8,
        "The feature should wait, because the team is at full capacity and two engineers "
        "are on holiday next week. The security fixes are due before the audit in October. "
        "Let's plan it for the next sprint.",
        True,
    ),
    _dev(
        10,
        "I would hire Ana. Both are strong technically, but Ana asked about the team and "
        "explained why she chose each tool, while Marco gave very short answers. This role "
        "involves a lot of work with clients, so communication matters more than raw speed.",
        False,
    ),
    _dev(
        10,
        "I would hire Ana, because she has ten years of experience with clients and speaks "
        "three languages, while Marco was late to the interview. Communication matters more "
        "than speed here.",
        True,
    ),
    _dev(
        12,
        "You create a branch, make your change and open a pull request for someone to "
        "review. Then the tests run in CI, and when everything is green you merge it. The "
        "pipeline deploys it to staging so you can check it, and on Tuesday and Thursday we "
        "deploy staging to production. It sounds slow, but we find most problems before "
        "customers do.",
        False,
    ),
    _dev(
        12,
        "You create a branch, open a pull request, and two reviewers must approve it. Then "
        "SonarQube scans the code, and the release manager deploys to production every "
        "Friday.",
        True,
    ),
]


HELD_OUT: list[Rewrite] = [
    _held(
        0,
        "A config change in the release pointed the app at the cache server we had "
        "switched off, so every request waited for the cache and gave up after about five "
        "seconds. That's why checkout was slow and then failed. One engineer noticed the "
        "cache errors after 40 minutes, and we fixed the config and redeployed. In short, "
        "config needs a review too, not only code.",
        False,
    ),
    _held(
        0,
        "A config change pointed the app at an old Redis server, so checkout failed for 40 "
        "minutes and about 300 customers could not pay. We fixed it and added a config "
        "review step to our pipeline.",
        True,
    ),
    _held(
        2,
        "We estimated three weeks and the work took five. Part of that was our fault, since "
        "we didn't include time for the security review, and part was the client, who asked "
        "for two changes in the middle, such as a new login page. Overall, we learned to "
        "plan with a buffer.",
        False,
    ),
    _held(
        2,
        "We estimated three weeks and the work took five, because the security review found "
        "a serious vulnerability in the login page and the client's lawyers asked for "
        "changes. We learned to plan with a buffer.",
        True,
    ),
    _held(
        4,
        "We picked Postgres mainly because of the reporting: the finance team runs complex "
        "queries every day with joins across six or seven tables, and SQL is made for that. "
        "Our backup system and monitoring already support Postgres, and although Mongo "
        "would be faster for writing documents, we write much less than we read. All in "
        "all, Postgres fits how we use the data.",
        False,
    ),
    _held(
        4,
        "We picked Postgres for the reporting, since the finance team's dashboards in "
        "Tableau need joins, and our last Mongo project lost data twice. Postgres fits how "
        "we use the data.",
        True,
    ),
    _held(
        6,
        "Adding it now would put the release at risk, because the sprint is already full "
        "and the payment retry work still needs two days of testing. I propose we finish "
        "the sprint as planned and then start the filter next sprint, and if the client "
        "can't wait, we can talk about dropping something else. It can wait two weeks.",
        False,
    ),
    _held(
        6,
        "Adding it now would put the release at risk, because the payment retry work failed "
        "QA twice and the CTO asked us to protect the launch date. It can wait two weeks.",
        True,
    ),
    _held(
        9,
        "I'd pick Sam. His answers were more concrete: when we asked about a conflict in a "
        "team, he gave us a real story with names and dates. He has worked in a small "
        "company, so he's used to doing a bit of everything. He's never led anyone, but this "
        "role doesn't need that yet.",
        False,
    ),
    _held(
        9,
        "I'd pick Sam, because his answers were concrete and his previous manager gave him "
        "an excellent reference. He also knows Kubernetes, which the other candidate didn't.",
        True,
    ),
    _held(
        11,
        "First I check whether the change is small enough to review, and if it's more than "
        "400 lines I ask the author to split it. Then I read the description and the ticket "
        "to understand the goal, and I go through the code file by file for correctness, "
        "readability and tests. I only approve when I'd be happy to maintain the code "
        "myself.",
        False,
    ),
    _held(
        11,
        "First I run the code locally and check that test coverage is above 80%. Then I read "
        "the code for security issues like SQL injection, and I only approve after the "
        "author fixes every comment.",
        True,
    ),
]
