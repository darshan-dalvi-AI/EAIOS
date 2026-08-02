"""The mock engine must never echo the prompt back at the user.

Observed in production: asking the Coding Agent about a client SOW returned

    Here is my take on "CONTEXT:
    If production availability falls below 99.5% in any calendar month during
    hypercare, a service credit of 5% of ": this instance is running the
    built-in mock engine, ...

Two failures compounded. The prompt splitter only recognised ``QUESTION:``,
but the coding agent writes ``REQUEST:`` — so the split failed and the whole
prompt became "the question". The fallback then quoted the first 120 characters
of that prompt, which was the *retrieved contract text*, and glued the
mock-mode notice into the middle of the sentence.
"""
import pytest

from app.llm.provider import NO_MODEL_PREFIX, MockLLM, _split_prompt

SOW = ("If production availability falls below 99.5% in any calendar month during "
       "hypercare, a service credit of 5% of the monthly fee applies. Excluded "
       "from scope: data migration and third-party licence costs.")


# ── the splitter understands every label the agents actually use ──────────

@pytest.mark.parametrize("label", [
    "QUESTION:",        # document, email, report, sql agents
    "REQUEST:",         # coding agent  ← the one that was broken
    "USER REQUEST:",    # custom agents ← also broken
    "TASK:",
    "INSTRUCTION:",
])
def test_every_agent_label_is_understood(label):
    context, question = _split_prompt(f"CONTEXT:\n{SOW}\n\n{label} What is excluded?")
    assert context.startswith("If production availability")
    assert question == "What is excluded?"


def test_user_request_wins_over_the_request_inside_it():
    """'USER REQUEST:' contains 'REQUEST:'. Matching the shorter one first would
    leave a stray 'USER ' on the end of the context."""
    context, question = _split_prompt(f"CONTEXT:\n{SOW}\n\nUSER REQUEST: What is excluded?")
    assert not context.endswith("USER")
    assert question == "What is excluded?"


def test_a_prompt_with_no_context_is_left_alone():
    assert _split_prompt("REQUEST: write a bubble sort") == ("", "REQUEST: write a bubble sort")


def test_context_with_no_recognisable_label_is_treated_as_context():
    """A future agent inventing a new label must not turn its retrieved
    documents into 'the question' — answering from them is the safe reading."""
    context, question = _split_prompt(f"CONTEXT:\n{SOW}\n\nWHATEVER: hello")
    assert context.startswith("If production availability")
    assert question == ""


# ── the exact production failure ──────────────────────────────────────────

def test_the_coding_agent_prompt_no_longer_echoes_the_document():
    """The regression, reproduced end to end."""
    prompt = (f"CONTEXT:\n{SOW}\n\nREQUEST: What is in scope for the current "
              "client SOW, and what is explicitly excluded?")
    answer = MockLLM().complete("You are the CODING Agent", prompt)

    assert not answer.startswith("Here is my take on")
    assert "CONTEXT:" not in answer
    assert NO_MODEL_PREFIX not in answer          # it had context; it must use it
    assert "Excluded from scope" in answer        # answered from the document


def test_the_fallback_never_quotes_the_prompt():
    """Even with an unparseable prompt, retrieved material must not be echoed.
    This is the guarantee that survives a future agent inventing a new label."""
    secret = "PATIENT RECORD: Jane Doe, diagnosed 2019, account 4471-9920"
    answer = MockLLM().complete("SYS", f"CONTEXT:\n{secret}\n\nZZZZ: summarise")
    assert "4471-9920" not in answer
    assert "Jane Doe" not in answer


def test_the_no_model_notice_is_a_whole_sentence():
    """It used to be spliced into the middle of an echoed fragment, producing
    '...a service credit of 5% of ": this instance is running...'."""
    answer = MockLLM().complete("SYS", "REQUEST: invent something for me")
    assert answer.startswith(NO_MODEL_PREFIX)
    assert '": ' not in answer


# ── confidence must reflect whether an answer was actually produced ───────

def test_coding_agent_reports_low_confidence_on_a_non_answer():
    """It hard-coded 78 regardless of outcome — including for the mock engine's
    'I cannot compose that' notice. A platform selling visible uncertainty
    cannot claim 78% on a non-answer."""
    from app.agents.coding_agent import CodingAgent

    assert CodingAgent.MIN_RELEVANCE > 0        # weak matches are dropped
    src = __import__("inspect").getsource(CodingAgent._run)
    assert "NO_MODEL_PREFIX" in src, "confidence must react to a degraded answer"
    assert "confidence=78" not in src
