"""The deterministic, fail-closed output validator."""

import unittest

from barq_support.agent.prompts import DECLINE_TEXT
from barq_support.agent.validation import validate_output

KNOWN = {"KB0010234", "KB0010301"}

GOOD = """STATUS: GROUNDED
Recommended resolution procedure (draft for human support agent review):
1. Test on a mobile hotspot. [KB0010234]
2. Reinstall the client. [KB0010301][KB0010234]
Sources:
- KB0010234 - Resolving VPN Error 809 on Windows
- KB0010301 - VPN Client Reset and Reinstall Procedure"""


class Validator(unittest.TestCase):
    def test_accepts_grounded_cited_answer(self):
        r = validate_output(GOOD, KNOWN)
        self.assertEqual(r.status, "GROUNDED")
        self.assertEqual(r.cited_articles, ["KB0010234", "KB0010301"])

    def test_accepts_markdown_bold_status(self):
        r = validate_output(GOOD.replace("STATUS: GROUNDED", "**STATUS: GROUNDED**"), KNOWN)
        self.assertEqual(r.status, "GROUNDED")

    def test_model_decline_is_canonicalised(self):
        r = validate_output("STATUS: DECLINED\nSorry, but you could try rebooting.", KNOWN)
        self.assertEqual(r.status, "DECLINED")
        self.assertEqual(r.text, DECLINE_TEXT)  # speculative leftovers are dropped
        self.assertEqual(r.decline_reason, "model_declined")

    def test_uncited_step_fails_closed(self):
        bad = GOOD.replace(" [KB0010234]\n2.", "\n2.")
        r = validate_output(bad, KNOWN)
        self.assertEqual(r.status, "DECLINED")
        self.assertIn("without a valid citation", r.decline_reason)

    def test_invented_article_fails_closed(self):
        r = validate_output(GOOD.replace("[KB0010301][KB0010234]", "[KB0099999]"), KNOWN)
        self.assertEqual(r.status, "DECLINED")
        self.assertIn("KB0099999", r.decline_reason)

    def test_missing_status_line_fails_closed(self):
        self.assertEqual(validate_output("1. do a thing [KB0010234]", KNOWN).status, "DECLINED")

    def test_no_numbered_steps_fails_closed(self):
        self.assertEqual(validate_output("STATUS: GROUNDED\nJust restart it.", KNOWN).status, "DECLINED")

    def test_empty_and_iteration_limit_messages_fail_closed(self):
        self.assertEqual(validate_output("", KNOWN).status, "DECLINED")
        self.assertEqual(
            validate_output("Agent stopped due to iteration limit or time limit.", KNOWN).status,
            "DECLINED",
        )

    def test_non_article_brackets_are_not_treated_as_citations(self):
        text = GOOD.replace("Test on a mobile hotspot.", "Set the value to [2] on the key.")
        self.assertEqual(validate_output(text, KNOWN).status, "GROUNDED")


if __name__ == "__main__":
    unittest.main()
