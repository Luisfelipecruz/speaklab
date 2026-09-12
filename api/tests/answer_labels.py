"""Hand-labelled spoken answers: how each one is built, marked by a person.

Each answer is something a learner could say to one of the seeded prompts, written the way
the recogniser writes speech down — sentence case, commas where the voice paused, digits
for numbers, contractions kept, a word said twice written twice. Every signpost in it is
marked by what it does, and so is every place the speaker said something twice or began a
phrase again.

**What is marked, and what is not.**

- A **reason** marks a cause, a purpose or a consequence: *because*, *because of*, *since*
  meaning because, *so* joining a result to its cause, *so that*, *that's why*, *the
  reason is*, *that way*. *since* meaning from a time is not one, *so* meaning very is
  not one, and *so has the team* is not one.
- An **example** introduces one: *for example*, *for instance*, *such as*, and *like*
  where it means for example. The last is marked because a teacher would mark it, even
  though no word list can tell it from the verb or the preposition.
- A **sequence** marks a step: *first*, *second*, *the first step*, *then* for what came
  next, *after that*, *next*, *finally*, *lastly*, *afterwards*, *to start with*. *then* in
  *if … then* is not one, nor *my first job*, *next week*, *a second* or *test it first*.
- A **contrast** sets one thing against another: *but*, *however*, *although*, *whereas*,
  *while* when it contrasts, *instead*, *on the other hand*, *nevertheless*, *even if*.
- A **close** sums up: *in short*, *overall*, *to sum up*, *in conclusion*, *bottom line*,
  and *so* opening the last sentence when that sentence sums up. *So* opening an answer
  is how people start talking, and is nothing. *the overall cost* is nothing.
- A **repeat** is a word or a run of words said twice in a row: *we we*, *the data, the
  data*. *again and again* is not one.
- A **restart** is a phrase abandoned and begun again differently: *the work, it took
  five*, *we need to, we have to*. The mark quotes the end of the abandoned phrase.

Addition (*also*, *besides*, *another point*) is not one of the functions, and a
sentence that sums up with no signpost in it has no close to mark.

**Two sets, both written before any code that counts them.** `DEVELOPMENT` is for building
the counter. `HELD_OUT` is for scoring it, and is not read while the counter is written;
if the counter is ever changed to pass one of its cases, the set is spent and a new one has
to be written first.

**The bars, set here before anything was measured.** A measure is shown to a learner only
if, on `HELD_OUT`, its precision is at least 0.90 and its recall at least 0.75, over at
least ten marked instances. Repeats and restarts must also reach the transcript: at least
half of those spoken in `ALOUD` must be written down by the recogniser. Sentences are
shown only if the recogniser's count is within one of the written count in at least three
answers of every four in `ALOUD`.

`ALOUD` is a third set, written to be spoken by the `tts` voice and heard by the
recogniser. Its fillers are written as words so the voice says them; whether the recogniser
writes them down, and the repeats, restarts, signposts and sentence ends, is what it
measures.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

REASON = "reason"
EXAMPLE = "example"
SEQUENCE = "sequence"
CONTRAST = "contrast"
CLOSE = "close"
REPEAT = "repeat"
RESTART = "restart"

SIGNPOSTS = (REASON, EXAMPLE, SEQUENCE, CONTRAST, CLOSE)
DISFLUENCIES = (REPEAT, RESTART)
KINDS = SIGNPOSTS + DISFLUENCIES


@dataclass(frozen=True)
class Mark:
    """One marked stretch: the words as they appear, what they do, and which occurrence."""

    quote: str
    kind: str
    nth: int = 1

    def span(self, transcript: str) -> tuple[int, int]:
        """Where the `nth` occurrence of the quote sits, as whole words, case as written."""
        pattern = re.compile(r"(?<![\w'])" + re.escape(self.quote) + r"(?![\w'])")
        found = list(pattern.finditer(transcript))
        assert len(found) >= self.nth, (self.quote, self.nth, transcript)
        match = found[self.nth - 1]
        return match.start(), match.end()


@dataclass(frozen=True)
class Answer:
    prompt: str
    transcript: str
    marks: tuple[Mark, ...] = field(default_factory=tuple)

    def of(self, kind: str) -> list[tuple[int, int]]:
        return [mark.span(self.transcript) for mark in self.marks if mark.kind == kind]


def r(quote: str, nth: int = 1) -> Mark:
    return Mark(quote, REASON, nth)


def e(quote: str, nth: int = 1) -> Mark:
    return Mark(quote, EXAMPLE, nth)


def s(quote: str, nth: int = 1) -> Mark:
    return Mark(quote, SEQUENCE, nth)


def c(quote: str, nth: int = 1) -> Mark:
    return Mark(quote, CONTRAST, nth)


def z(quote: str, nth: int = 1) -> Mark:
    return Mark(quote, CLOSE, nth)


def rep(quote: str, nth: int = 1) -> Mark:
    return Mark(quote, REPEAT, nth)


def rst(quote: str, nth: int = 1) -> Mark:
    return Mark(quote, RESTART, nth)


# ── Development ─────────────────────────────────────────────────────────────

DEVELOPMENT: list[Answer] = [
    Answer(
        "explain-a-failed-release",
        "Yesterday we released the new checkout, and it broke payments for about an "
        "hour. The problem started because the new version expected a field that the old "
        "mobile app does not send. So every payment from the app failed. We didn't see it "
        "in testing, because our test data only had web orders. First we thought it was "
        "the payment provider, but their status page was green. Then we checked the logs "
        "and we saw the error, and we rolled back. In short, it was a missing field and a "
        "gap in our test data.",
        (
            r("because"),
            r("So"),
            r("because", 2),
            s("First"),
            c("but"),
            s("Then"),
            z("In short"),
        ),
    ),
    Answer(
        "explain-a-failed-release",
        "So the release, the release on Tuesday failed. We we changed the database "
        "schema, and the migration took longer than we expected. Because of that, the site "
        "was down for 20 minutes. I think the main mistake was, it was that we ran the "
        "migration at peak time. Next time we will run it at night, and we will test it on "
        "a copy of production first. So overall, the code was fine, but the timing was "
        "wrong.",
        (
            rep("the release, the release"),
            rep("We we"),
            r("Because of that"),
            rst("main mistake was"),
            z("So overall"),
            c("but"),
        ),
    ),
    Answer(
        "explain-a-missed-deadline",
        "We promised the client the export feature by the end of March, and we delivered "
        "it two weeks late. There were two reasons. The first reason is that the client "
        "changed the file format in the middle of the project. The second reason is that "
        "one of our developers was sick for a week. Although we warned the client about "
        "the risk, we did not give them a new date early enough. That's why they were "
        "surprised. To sum up, the delay was partly outside our control, but we should "
        "have communicated better.",
        (
            s("The first reason"),
            s("The second reason"),
            c("Although"),
            r("That's why"),
            z("To sum up"),
            c("but"),
        ),
    ),
    Answer(
        "explain-a-missed-deadline",
        "Um, so we missed the date because the the integration with their system was "
        "harder than we thought. Their API had no, there was no documentation, so we had "
        "to guess how it worked. For example, the dates came in three different formats. "
        "We asked them for help, but they took a week to answer. I mean, I understand, "
        "they are busy, but it cost us time. Anyway, we are finished now and the feature "
        "is live.",
        (
            r("because"),
            rep("the the"),
            rst("API had no"),
            r("so", 2),
            e("For example"),
            c("but"),
            c("but", 2),
        ),
    ),
    Answer(
        "explain-a-slow-report",
        "Thank you for waiting. The reports page is slow because it calculates everything "
        "again every time you open it. When you have a lot of orders, like more than ten "
        "thousand, this takes a long time. We are changing it so that the numbers are "
        "calculated once at night. After that, the page will open in one or two seconds. "
        "Until then, you can use the export, which is faster. I'm sorry for the trouble.",
        (
            r("because"),
            e("like"),
            r("so that"),
            s("After that"),
        ),
    ),
    Answer(
        "explain-a-slow-report",
        "Okay, so the problem is not your computer. The page loads all your data at once, "
        "and since you have five years of data, it is very slow. We have seen this with "
        "other customers too. There are two things you can do. First, you can choose a "
        "shorter period, for example the last month. Second, you can ask us to archive the "
        "old data. But the real fix is on our side, and we are working on it.",
        (
            r("since"),
            s("First"),
            e("for example"),
            s("Second"),
            c("But"),
        ),
    ),
    Answer(
        "justify-a-database-choice",
        "I chose Postgres for three reasons. First of all, our data is very, it's very "
        "relational, we have customers, orders and invoices, and they all reference each "
        "other. Secondly, we need transactions, because a payment and an invoice must be "
        "saved together or not at all. Thirdly, the team already knows SQL. MongoDB is good "
        "for some things, such as storing documents with a flexible shape. However, we "
        "don't have that problem. So I think Postgres is the safer choice for this service.",
        (
            s("First of all"),
            rst("data is very"),
            s("Secondly"),
            r("because"),
            s("Thirdly"),
            e("such as"),
            c("However"),
            z("So"),
        ),
    ),
    Answer(
        "justify-a-database-choice",
        "Well, I know you like Mongo, and it's a good database. But for this service we "
        "need to join a lot of tables. With Mongo we would have to do the joins in the "
        "code, and that is slow and easy to get wrong. Also we we need strong consistency. "
        "For instance, if two people book the same room, only one booking can win. "
        "Postgres gives us that with a unique constraint. So that's why I picked it.",
        (
            c("But"),
            rep("we we"),
            e("For instance"),
            z("So"),
            r("that's why"),
        ),
    ),
    Answer(
        "push-back-on-scope",
        "I understand the feature is important to the client, but I think we should not "
        "add it to this sprint. We already committed to, we already promised eight "
        "stories, and the team is at full capacity. If we add it now, then something else "
        "will slip, probably the security fixes. Those fixes are due before the audit, so "
        "they cannot move. Instead, I suggest we plan the feature for the next sprint, and "
        "I can start the design this week. That way the client gets it in three weeks, and "
        "we keep our promises.",
        (
            c("but"),
            rst("already committed to"),
            r("so"),
            c("Instead"),
            r("That way"),
        ),
    ),
    Answer(
        "push-back-on-scope",
        "Honestly, I think it is a bad idea to add it now. The the reason is simple, we "
        "don't have time to test it properly. Last time we added something at the end of a "
        "sprint, we had a bug in production for two days. On the other hand, if the client "
        "really needs it, we could drop the dashboard story. But we need to decide that "
        "together, with the product owner. So, in summary, I would wait, or we swap it "
        "with something.",
        (
            rep("The the"),
            r("reason is"),
            c("On the other hand"),
            c("But"),
            z("So, in summary"),
        ),
    ),
    Answer(
        "choose-a-candidate",
        "I would hire Ana. Both candidates are strong technically, but they are different "
        "in how they work with people. Ana asked us a lot of questions about the team, and "
        "she explained her decisions clearly. For example, when we asked about her last "
        "project, she told us why she chose each tool and what she would change. Marco, on "
        "the other hand, gave very short answers. He is probably a better programmer, "
        "although it's hard to be sure after one hour. However, this role involves a lot "
        "of work with clients, so communication matters more than raw speed. Overall, I "
        "think Ana is the better fit.",
        (
            c("but"),
            e("For example"),
            c("on the other hand"),
            c("although"),
            c("However"),
            r("so"),
            z("Overall"),
        ),
    ),
    Answer(
        "choose-a-candidate",
        "Okay, I have a clear preference, it's the second candidate, Lee. First, his code "
        "in the take-home test was clean and it had tests. The other candidate's code "
        "worked, but there were no tests at all. Then in the interview, Lee was, he was "
        "honest when he didn't know something. I like that, because it means he will ask "
        "for help instead of guessing. The only risk is that he has less experience with "
        "our stack. To be honest that's something we can teach. So my recommendation is "
        "Lee.",
        (
            s("First"),
            c("but"),
            s("Then"),
            rst("Lee was"),
            r("because"),
            c("instead of"),
            z("So"),
        ),
    ),
    Answer(
        "walk-through-a-release",
        "Okay, I'll explain how a change goes to production here. First you create a "
        "branch and you make your change. Then you open a pull, a pull request, and "
        "someone from the team reviews it. After that, the tests run automatically in CI. "
        "If everything is green, you merge it. Then the pipeline deploys it to staging, "
        "and you check it there. Finally, on Tuesday and Thursday we deploy staging to "
        "production. It sounds slow, but it means we find most problems before customers "
        "do.",
        (
            s("First"),
            s("Then"),
            rep("a pull, a pull"),
            s("After that"),
            s("Then", 2),
            s("Finally"),
            c("but"),
        ),
    ),
    Answer(
        "walk-through-a-release",
        "So there are, um, four steps. The first step is to write the code and the tests on "
        "your own branch. The second step is the review. We need one approval, but for big "
        "changes we ask for two. Next, you merge to main and the pipeline builds a Docker "
        "image. The last step is the deploy, which is automatic, and then you watch the "
        "dashboards for ten minutes. You watch them because sometimes a problem only "
        "appears with real traffic.",
        (
            s("The first step"),
            s("The second step"),
            c("but"),
            s("Next"),
            s("The last step"),
            s("then"),
            r("because"),
        ),
    ),
    Answer(
        "walk-through-a-code-review",
        "When I review a pull request, I start with the description, because I need to "
        "know what problem it solves. Then I read the tests before the code. If the tests "
        "are clear, the code is usually clear too. After that I look at the code itself, "
        "and I check the names, the error, how errors are handled and the edge cases, for "
        "example what happens with an empty list. I try to leave questions instead of "
        "orders, like, why did you choose this approach. Finally, I approve it, or I ask "
        "for changes and explain why.",
        (
            r("because"),
            s("Then"),
            s("After that"),
            rst("the error"),
            e("for example"),
            c("instead of"),
            e("like"),
            s("Finally"),
        ),
    ),
    Answer(
        "walk-through-a-code-review",
        "I have a, I have a checklist that I follow. First, does the code do what the "
        "ticket says? Second, is it tested, and do the tests fail if you break the code? "
        "Third, is it readable for someone new. I don't comment on style, since the linter "
        "does that for us. However I do comment on names, because names are the "
        "documentation that nobody skips. And at the end I always say one thing I liked, "
        "so that the review doesn't feel like only criticism.",
        (
            rep("I have a, I have a"),
            s("First"),
            s("Second"),
            s("Third"),
            r("since"),
            c("However"),
            r("because"),
            s("at the end"),
            r("so that"),
        ),
    ),
    Answer(
        "walk-through-an-alert",
        "When an alert fires at night, the first thing you do is acknowledge it, so that "
        "the rest of the team knows someone is on it. Then you open the runbook for that "
        "alert. Every alert has a runbook, and it tells you what to check first. For "
        "example, for the disk space alert, you check which service is writing the big "
        "files. If you can fix it with the runbook, you fix it and you write a short note. "
        "But if you can't fix it in thirty minutes, you call the, you call the second "
        "person on the rota. Don't try to be a hero, because a tired person at 3am makes "
        "mistakes. In the morning, we review what happened together.",
        (
            s("the first thing"),
            r("so that"),
            s("Then"),
            e("For example"),
            c("But"),
            rep("you call the, you call the"),
            r("because"),
        ),
    ),
    Answer(
        "walk-through-an-alert",
        "Okay so the process has three parts, detect, fix, and learn. Um, detection is "
        "automatic, the alert pages you on your phone. To fix it, you start with the "
        "dashboard for that service, because it shows you if the problem is traffic, "
        "errors or the database. Then you, then you decide if you need to roll back. "
        "Rolling back is always allowed, even if you're not sure, since it's cheap. Then "
        "later, when it's fixed, you write the incident report. The report is not about "
        "blame, it's about what we change so it doesn't happen again.",
        (
            r("because"),
            s("Then"),
            rep("Then you, then you"),
            c("even if"),
            r("since"),
            s("Then", 2),
            r("so", 2),
        ),
    ),
    Answer(
        "recommend-a-tool",
        "I recommend Trello for our team. It's simple, and everybody can learn it in one "
        "day. We tried Jira in my, in my last company, but it had too many options and "
        "people stopped using it. With Trello you just have columns, like to do, doing and "
        "done. Also it's free for small teams, so we don't need to ask for a budget. So "
        "for a team of six people, I think Trello is enough.",
        (
            rep("in my, in my"),
            c("but"),
            e("like"),
            r("so"),
            z("So"),
        ),
    ),
    Answer(
        "recommend-a-tool",
        "My recommendation is Linear. The main reason is speed, the interface is really "
        "fast and you can do everything with the keyboard. It also connects with GitHub, "
        "so when you merge a pull request the ticket closes by itself. The problem is the "
        "price, it's eight dollars per person per month. However, we would save time every "
        "day, which is worth more than the price. To conclude, I would try it for one "
        "month and then decide.",
        (
            r("The main reason is"),
            r("so"),
            c("However"),
            z("To conclude"),
            s("then"),
        ),
    ),
    Answer(
        "recommend-office-days",
        "I would recommend two days in the office, not more. On one side, people need to "
        "meet, to see each other in person, especially new people, because they learn a "
        "lot by listening to others. On the other side, most of our work is deep work, and "
        "the office is noisy. We also have colleagues who live one hour away, and for them "
        "five days is too much. So I would pick two fixed days, for example Tuesday and "
        "Thursday, when the whole team is there. That way meetings happen on those days and "
        "the other days are quiet.",
        (
            c("On one side"),
            rst("to meet"),
            r("because"),
            c("On the other side"),
            r("So"),
            e("for example"),
            r("That way"),
        ),
    ),
    Answer(
        "recommend-office-days",
        "In my opinion, we should keep it flexible. Every team is different. For instance, "
        "the support team needs to be together, but the data team works better from home. "
        "If we force three days for everybody, we will lose people, since other companies "
        "offer full remote. So my proposal is that each team decides, with a minimum of "
        "one day per month for everybody. In short, a rule for the team, not for the "
        "company.",
        (
            e("For instance"),
            c("but"),
            r("since"),
            r("So"),
            z("In short"),
        ),
    ),
    Answer(
        "recommend-a-priority",
        "I'd go for the technical debt, and I know that's not the popular answer. Right "
        "now every new feature takes us, it takes us twice as long as it did a year ago, "
        "because the billing code is so tangled. Customers want the new reports, sure, but "
        "if we build them on top of that code, they'll be late and they'll be buggy. So "
        "I'd spend the quarter cleaning up billing first. Then the reports will take maybe "
        "half the time, and we can ship them early next quarter. Having said that, we "
        "should tell customers now when the reports are coming, so that they don't feel "
        "ignored.",
        (
            rst("feature takes us"),
            r("because"),
            c("but"),
            r("So"),
            s("Then"),
            c("Having said that"),
            r("so that"),
        ),
    ),
    Answer(
        "recommend-a-priority",
        "I recommend the feature. The technical debt is real, I don't, I don't deny it. "
        "But customers have asked for this feature for a year, and two of them said they "
        "might leave. Losing a big customer costs more than slow development. What I would "
        "do is build the feature, and at the same time fix the worst parts of the debt that "
        "the feature touches. That way we get both, partly. So, to sum up, customers first, "
        "and debt in small pieces.",
        (
            rep("I don't, I don't"),
            c("But"),
            r("That way"),
            z("So, to sum up"),
        ),
    ),
]


# ── Held out ────────────────────────────────────────────────────────────────

HELD_OUT: list[Answer] = [
    Answer(
        "explain-a-failed-release",
        "What happened is that a config change went out with the release. The config "
        "pointed the app at the old, at the cache server that we had switched off the week "
        "before. As soon as the release went live, every request waited for the cache, and "
        "after about five seconds it gave up. That's why checkout was so slow and then "
        "failed. We found it after 40 minutes, because one engineer noticed the cache "
        "errors in the logs. We fixed the config, redeployed, and it recovered. The lesson "
        "for us is that config needs a review too, not only code. So in short, a one-line "
        "config change took checkout down.",
        (
            rst("at the old"),
            r("That's why"),
            s("then"),
            r("because"),
            z("So in short"),
        ),
    ),
    Answer(
        "explain-a-failed-release",
        "Right, so, the outage. We deployed at five, and the the new search service "
        "couldn't, it couldn't connect to the database. The reason was a password. The "
        "password was rotated on Monday, but nobody updated it in the the deployment "
        "secrets. So the service started, it failed, and it started again, again and "
        "again. I was, I was on call, so I rolled back at five fifteen. After that "
        "everything worked. Honestly the fix is easy, we just need an alert when a secret "
        "is older than the service.",
        (
            rep("the the"),
            rst("service couldn't"),
            r("The reason was"),
            c("but"),
            rep("the the", 2),
            r("So"),
            rep("I was, I was"),
            r("so", 2),
            s("After that"),
        ),
    ),
    Answer(
        "explain-a-missed-deadline",
        "The honest answer is that we underestimated it. We estimated three weeks, but the "
        "work, it took five. Part of that was our fault, since we didn't include time for "
        "the security review. The other part was the client, who asked for two changes in "
        "the middle, such as a new login page. We should have said the date would move "
        "when they asked for the changes. Next time I'd put every change request in "
        "writing with its cost in days. Overall, we learned to plan with a buffer.",
        (
            c("but"),
            rst("the work"),
            r("since"),
            e("such as"),
            z("Overall"),
        ),
    ),
    Answer(
        "explain-a-slow-report",
        "I'm sorry the report is slow, and I can explain why. Your account has much more "
        "data than most, around two million rows. The report reads all of them every time, "
        "so it takes about ten seconds. We've known about this since last year, but it "
        "only affects a few customers, so it wasn't a priority. Now it is. We're going to, "
        "we're building a summary table, and once it's ready the report will read that "
        "instead. That should be ready in two weeks. In the meantime, if you filter by "
        "month first, it will be much faster.",
        (
            r("so"),
            c("but"),
            r("so", 2),
            rst("We're going to"),
            c("instead"),
        ),
    ),
    Answer(
        "justify-a-database-choice",
        "We picked Postgres mainly because of the reporting. The finance team runs, they "
        "run complex queries every day, with joins across six or seven tables, and SQL is "
        "made for that. Mongo can do aggregations, however they get complicated very "
        "quickly. Another point is the tooling, for instance our backup system and our "
        "monitoring already support Postgres. And to be fair, Mongo would be faster for "
        "writing documents, but we write much less than we read. So all in all, Postgres "
        "fits how we use the data.",
        (
            r("because of"),
            rst("finance team runs"),
            c("however"),
            e("for instance"),
            c("but"),
            z("So all in all"),
        ),
    ),
    Answer(
        "justify-a-database-choice",
        "So I, I chose Postgres, and let me explain. First, the data, the data has a fixed "
        "structure, users, accounts, transactions. We know the schema, so we don't need a "
        "schemaless database. Second, I've used Postgres for, for six years, and so has "
        "most of the team. Then there's cost. It's free, and our cloud provider manages it "
        "for us. I know Mongo is popular, but popular is not a reason. To sum up, it's the "
        "tool we know, for data it fits.",
        (
            rep("I, I"),
            s("First"),
            rep("the data, the data"),
            r("so"),
            s("Second"),
            rep("for, for"),
            s("Then"),
            c("but"),
            z("To sum up"),
        ),
    ),
    Answer(
        "push-back-on-scope",
        "I get why you want it, but adding it now would put the release at risk. The sprint "
        "is already full. For example, the payment retry work still needs two days of "
        "testing. If we squeeze the new filter in, something has to, something will have "
        "to give, and I don't want it to be testing. What I propose is to finish this "
        "sprint as planned and then start the filter first thing next sprint. "
        "Nevertheless, if the client can't wait, I'm happy to talk about dropping "
        "something else. Bottom line, it can wait two weeks.",
        (
            c("but"),
            e("For example"),
            rst("something has to"),
            s("then"),
            c("Nevertheless"),
            z("Bottom line"),
        ),
    ),
    Answer(
        "push-back-on-scope",
        "Um, I think we, we shouldn't. The team is tired, we've had three long sprints. If "
        "we add more work, people will make mistakes, and mistakes in this area are "
        "expensive, like the billing bug last month. Besides, the feature isn't fully "
        "designed yet. We would be building something that is going to change. Although I "
        "understand the pressure from sales, I think it's better to say no this time. So, "
        "in short, not in this sprint.",
        (
            rep("we, we"),
            e("like"),
            c("Although"),
            z("So, in short"),
        ),
    ),
    Answer(
        "choose-a-candidate",
        "I'd choose Priya over Tom. Tom has more years of experience, while Priya has "
        "experience that's closer to what we do, she built a, she designed a payment system "
        "from scratch. During the system design question, she started by asking about the "
        "scale, whereas Tom went straight into drawing boxes. That tells me she thinks "
        "before she builds. On top of that, her references were excellent. The one concern "
        "is salary, since she asked for more than our range. But I think she's worth it. "
        "In conclusion, Priya.",
        (
            c("while"),
            rst("she built a"),
            c("whereas"),
            r("since"),
            c("But"),
            z("In conclusion"),
        ),
    ),
    Answer(
        "choose-a-candidate",
        "It was, it was a hard decision, because they were both good. In the end I'd pick "
        "Sam. Sam's, Sam's answers were more concrete. For instance, when we asked about a "
        "conflict in a team, he gave us a real story with names and dates. The other "
        "candidate talked in general terms. Also, Sam has worked in a small company "
        "before, so he's used to doing a bit of everything. The risk is that he's never "
        "led anyone, but this role doesn't need that yet. Overall, Sam.",
        (
            rep("It was, it was"),
            r("because"),
            z("In the end"),
            rep("Sam's, Sam's"),
            e("For instance"),
            r("so"),
            c("but"),
            z("Overall"),
        ),
    ),
    Answer(
        "walk-through-a-release",
        "Here's how it works. To start with, every change needs a ticket, so we know why "
        "it exists. You write the code on a, on your own branch, and you push it. The CI "
        "pipeline runs the checks, such as the linter and the tests, which takes about "
        "eight minutes. Once it's green, you ask for a review in the team channel. When "
        "it's approved, you squash and merge. The deploy to production happens "
        "automatically after that, but only between nine and four, so that somebody is "
        "around if something breaks. That's the whole process, it's simpler than it "
        "sounds.",
        (
            s("To start with"),
            r("so"),
            rst("on a"),
            e("such as"),
            s("after that"),
            c("but"),
            r("so that"),
        ),
    ),
    Answer(
        "walk-through-a-code-review",
        "The first thing I check is whether the change is small enough to review. If it's "
        "more than 400 lines, I ask, I tell the author to split it. Then I read the "
        "description and the ticket, so I understand the goal. After that I go through the "
        "code file by file. I look for three things in particular, correctness, "
        "readability and tests. For example, if a function has five parameters, that's a "
        "readability problem. I try to be kind in the comments, but clear. Lastly, I only "
        "approve when I'd be happy to maintain the code myself.",
        (
            s("The first thing"),
            rst("I ask"),
            s("Then"),
            r("so"),
            s("After that"),
            e("For example"),
            c("but"),
            s("Lastly"),
        ),
    ),
    Answer(
        "walk-through-an-alert",
        "First of all, don't panic. The alert, the alert tells you which service is "
        "affected. You open the dashboard, and you check the error rate. If the error rate "
        "is high, then you look at what changed recently, for example a deploy or a config "
        "change. Most of the time it's a deploy, so you, you roll it back. If it's not a "
        "deploy, you follow the runbook. And if you're stuck, call your backup, even at "
        "3am, because that's what they're there for. Afterwards, we write it up, and nobody "
        "gets blamed.",
        (
            s("First of all"),
            rep("The alert, the alert"),
            e("for example"),
            r("so"),
            rep("you, you"),
            r("because"),
            s("Afterwards"),
        ),
    ),
    Answer(
        "recommend-a-tool",
        "I'd recommend Notion for the documentation. At the moment our docs are in three "
        "places, Google Docs, the wiki and people's heads, and nobody can find anything. "
        "Notion puts everything in, it puts everything in one place, and the search is "
        "actually good. Also it has templates, for example for meeting notes and for "
        "incident reports. The downside is that it can get messy if nobody owns it. So we "
        "would need one person to organise it at the start. Anyway, overall I think it's "
        "worth trying.",
        (
            rst("Notion puts everything in"),
            e("for example"),
            r("So"),
            z("overall"),
        ),
    ),
    Answer(
        "recommend-office-days",
        "I'd say three days. I know that's more than some people want. But look at the "
        "numbers, since we went fully remote, onboarding takes twice as long. New people, "
        "new people especially need to sit next to someone. Of course, three days is hard "
        "for parents. So I'd make the days flexible, for example you choose which three. "
        "Also, the office is only worth it if the team is there on the same days. In "
        "summary, three days, chosen by each team.",
        (
            c("But"),
            rep("New people, new people"),
            r("So"),
            e("for example"),
            z("In summary"),
        ),
    ),
    Answer(
        "recommend-a-priority",
        "My view is that we should do the feature customers are asking for, but with a "
        "condition. Because if we spend the whole quarter on technical debt, customers "
        "won't see anything, and sales will have nothing new to sell. The condition is that "
        "we reserve, we keep 20% of every sprint for the debt. That way the debt goes down "
        "slowly, and it doesn't stop us. For instance, the flaky tests could be fixed in "
        "the first two sprints. However, if the debt starts causing outages, then we stop "
        "and fix it. To sum up, the feature first, with a steady 20% for the debt.",
        (
            c("but"),
            r("Because"),
            rst("we reserve"),
            r("That way"),
            e("For instance"),
            c("However"),
            z("To sum up"),
        ),
    ),
]


# ── Readings of a word with another use ─────────────────────────────────────
#
# One sentence each, and the function the word has in it, or None where it is not a
# signpost. Part of the development set: these are what the counter is built against.

READINGS: list[tuple[str, str, str | None]] = [
    ("It failed, so we rolled back.", "so", REASON),
    ("The page was so slow that customers left.", "so", None),
    ("I think so.", "so", None),
    ("We changed the timeout so that the job can finish.", "so", REASON),
    ("The tests passed. So we merged it. Then we deployed.", "So", REASON),
    ("I have used it for years, and so has the team.", "so", None),
    ("We have worked here since 2019.", "since", None),
    ("Since the deploy failed, we rolled back.", "Since", REASON),
    ("We have had two outages since we moved to the new cluster.", "since", None),
    ("Since it was late, we stopped.", "Since", REASON),
    ("I like the new dashboard.", "like", None),
    ("Tools like Jira have too many options.", "like", None),
    ("It looks like a network problem.", "like", None),
    ("If it fails, then we roll back.", "then", None),
    ("We build it, then we test it.", "then", SEQUENCE),
    ("Back then we had no tests.", "then", None),
    ("Until then, use the export.", "then", None),
    ("First, we check the logs.", "First", SEQUENCE),
    ("My first job was in a bank.", "first", None),
    ("The first step is the review.", "first", SEQUENCE),
    ("Test it on staging first.", "first", None),
    ("Wait a second.", "second", None),
    ("Second, the tests must pass.", "Second", SEQUENCE),
    ("Next week we deploy.", "Next", None),
    ("Next, we merge it.", "Next", SEQUENCE),
    ("Nothing but the logs helped.", "but", None),
    ("It works, but it is slow.", "but", CONTRAST),
    ("The overall cost is lower.", "overall", None),
    ("Overall, it was a good week.", "Overall", CLOSE),
    ("Finally, we deploy it.", "Finally", SEQUENCE),
    ("We are not there yet.", "yet", None),
    ("It is slow, yet it works.", "yet", CONTRAST),
    ("While you wait, read the runbook.", "While", None),
    ("Tom is fast, while Ana is careful.", "while", CONTRAST),
    ("It is late, though.", "though", CONTRAST),
    ("At the end of the day we ship it.", "At the end", None),
    ("And at the end we write the report.", "at the end", SEQUENCE),
]


# ── Said aloud ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Spoken:
    """An answer for the voice to say, with what it holds that the recogniser might drop.

    `fillers` is how many filler words the text contains. Repeats and restarts are quoted
    with the words that follow them, so that what reaches the transcript can be looked for
    as a run of words: a repeat is heard if both copies are, and a restart if the abandoned
    words are heard followed by the new start.
    """

    prompt: str
    text: str
    fillers: int
    repeats: tuple[str, ...]
    restarts: tuple[str, ...]
    signposts: tuple[str, ...]


ALOUD: list[Spoken] = [
    Spoken(
        "explain-a-failed-release",
        "The release failed yesterday afternoon. Um, the new version needed a database "
        "column that, that was not there yet. Because of that, every request to the orders "
        "page failed. We, we did not notice for twenty minutes, because the alert was, "
        "somebody had switched the alert off. Then we rolled back, uh, and the site "
        "recovered. In short, we deployed the code before the migration.",
        2,
        ("that, that", "We, we"),
        ("the alert was, somebody",),
        ("Because of that", "because", "Then", "In short"),
    ),
    Spoken(
        "explain-a-missed-deadline",
        "We delivered the export two weeks late. Um, the main reason is that the client "
        "changed the file format, the format in the middle of the project. We should have, "
        "we could have asked for more time. But we did not, uh, we did not say anything "
        "until the last week. To sum up, the work was fine and the communication was not.",
        2,
        ("the file format, the format", "we did not, uh, we did not"),
        ("We should have, we could",),
        ("the main reason is", "But", "To sum up"),
    ),
    Spoken(
        "explain-a-slow-report",
        "The report is slow because it reads every order you have ever made. For example, "
        "you have about two million orders. Um, we are going to, we are building a summary "
        "table this month. After that, the page will open in, in one second. Until the "
        "change is ready, uh, you can use the export instead. So the fix is coming soon.",
        2,
        ("in, in",),
        ("we are going to, we are building",),
        ("because", "For example", "After that", "instead", "So"),
    ),
    Spoken(
        "justify-a-database-choice",
        "I chose Postgres for two reasons. First, our data, our data is very relational. "
        "Um, customers, orders and invoices all point at each other. Second, we need "
        "transactions, because a payment and an invoice must be saved together. Mongo is "
        "good for, it is great for flexible documents. However, uh, we do not have that "
        "problem. So overall, Postgres is the safer choice.",
        2,
        ("our data, our data",),
        ("good for, it is great",),
        ("First", "Second", "because", "However", "So overall"),
    ),
    Spoken(
        "push-back-on-scope",
        "I understand the feature matters, but I think it should wait. The sprint is, the "
        "sprint is already full. Um, if we add it now, the security fixes will slip. Those "
        "fixes are due before the audit, so they cannot move. Instead, I suggest we, uh, we "
        "plan it for the next sprint. That way the client gets it in three weeks.",
        2,
        ("The sprint is, the sprint is", "we, uh, we"),
        (),
        ("but", "so", "Instead", "That way"),
    ),
    Spoken(
        "choose-a-candidate",
        "I would hire Ana. Both candidates are strong, but Ana explains her decisions "
        "clearly. Um, for instance, she told us why she chose each tool. Marco is, Marco "
        "gave very short answers. He may be the better programmer, although, uh, it is hard "
        "to be sure after one hour. This role involves a lot of work with clients, so "
        "communication matters more. Overall, Ana is the better fit.",
        2,
        (),
        ("Marco is, Marco gave",),
        ("but", "for instance", "although", "so", "Overall"),
    ),
    Spoken(
        "walk-through-a-release",
        "Here is how a change reaches production. First, you create a branch, a branch "
        "for your change. Then you open a pull request, um, and someone reviews it. After "
        "that, the tests run in the pipeline. If everything is green, you merge it. "
        "Finally, uh, the pipeline deploys it on Tuesday or Thursday. It sounds slow, but "
        "we find most problems before our customers do.",
        2,
        ("a branch, a branch",),
        (),
        ("First", "Then", "After that", "Finally", "but"),
    ),
    Spoken(
        "walk-through-a-code-review",
        "I start with the description, because I need to know the goal. Then I read the, "
        "the tests before the code. Um, after that I look at the names and the error "
        "handling. I try to, I like to ask questions instead of giving orders. For example, "
        "why did you choose this approach? Finally, uh, I approve it or I ask for changes.",
        2,
        ("the, the",),
        ("I try to, I like",),
        ("because", "Then", "after that", "instead of", "For example", "Finally"),
    ),
    Spoken(
        "walk-through-an-alert",
        "First of all, do not panic. Um, the alert tells you which service is affected. You "
        "open the dashboard, the dashboard for that service. If a deploy caused it, you "
        "roll it back, because rolling back is always allowed. If you are stuck, uh, you "
        "call your backup. Afterwards, we write it up, and we write, nobody is blamed.",
        2,
        ("the dashboard, the dashboard",),
        ("we write, nobody",),
        ("First of all", "because", "Afterwards"),
    ),
    Spoken(
        "recommend-a-tool",
        "I recommend Trello for our team. It is simple, and everybody can learn it in one "
        "day. Um, we tried Jira in my, in my last company, but it had too many options. "
        "Trello is free for, uh, it costs nothing for small teams, so we do not need a "
        "budget. So for a team of six, Trello is enough.",
        2,
        ("in my, in my",),
        ("free for, uh, it costs",),
        ("but", "so", "So"),
    ),
    Spoken(
        "recommend-office-days",
        "I would recommend two days in the office. On the one hand, new people learn a lot "
        "by sitting next to others. Um, on the other hand, the office is noisy, and deep "
        "work is, deep work is easier at home. So I would pick two fixed days, for example "
        "Tuesday and Thursday. Uh, that way the whole team is there on the same days. In "
        "summary, two days, the same for everyone.",
        2,
        ("deep work is, deep work is",),
        (),
        (
            "On the one hand",
            "on the other hand",
            "So",
            "for example",
            "that way",
            "In summary",
        ),
    ),
    Spoken(
        "recommend-a-priority",
        "I would choose the technical debt. Every new feature takes us, it takes us twice "
        "as long as a year ago. Um, the billing code is so tangled that every change "
        "breaks something. Customers want the new reports, but if we build them on that "
        "code, they will be late. Then, uh, after the clean up, the reports will take half "
        "the time. To sum up, debt first, and the reports right after.",
        2,
        (),
        ("takes us, it takes us",),
        ("but", "Then", "To sum up"),
    ),
]
