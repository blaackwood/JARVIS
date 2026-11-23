import unittest
from unittest.mock import patch

from core import screenview
from actions import screen_perception as module


def make_view(elements=None, degraded=False, source="uia"):
    return screenview.View(
        source=source, degraded=degraded, app="test.exe", title="Test",
        elements=list(elements or []), digest="fresh", stable_digest="fresh",
    )


class ScreenPerceptionTests(unittest.TestCase):
    def test_inspect_returns_screen_metadata(self):
        view = make_view()
        with patch.object(module.screenview, "look", return_value=view):
            result = module.screen_perception({"action": "inspect"})
        self.assertIn("SCREEN_READ source=uia", result)
        self.assertIn("test.exe", result)

    def test_degraded_view_blocks_interaction(self):
        view = make_view(degraded=True, source="ocr")
        with patch.object(module.screenview, "look", return_value=view), \
             patch.object(module.screenact, "click") as click:
            result = module.screen_perception({"action": "click", "target": "OK"})
        self.assertIn("SCREEN_UNAVAILABLE", result)
        click.assert_not_called()

    def test_exact_unique_button_can_be_clicked(self):
        el = screenview.Element(1, screenview.ROLE_BUTTON, "Open", "", 10, 10, 80, 30)
        view = make_view([el])
        from core.screenact import Act
        with patch.object(module.screenview, "look", return_value=view), \
             patch.object(module.screenact, "click", return_value=Act(True, "click", target="Open")) as click:
            result = module.screen_perception({"action": "click", "target": "Open"})
        click.assert_called_once_with(el, button="left", clicks=1)
        self.assertIn("ACTION_DELIVERED_NOT_VERIFIED", result)

    def test_ambiguous_exact_labels_do_not_click(self):
        a = screenview.Element(1, screenview.ROLE_BUTTON, "Open", "", 10, 10, 80, 30)
        b = screenview.Element(2, screenview.ROLE_BUTTON, "Open", "", 100, 10, 80, 30)
        with patch.object(module.screenview, "look", return_value=make_view([a, b])), \
             patch.object(module.screenact, "click") as click:
            result = module.screen_perception({"action": "click", "target": "Open"})
        self.assertIn("AMBIGUOUS_TARGET", result)
        click.assert_not_called()

    def test_type_only_targets_edit_and_refuses_protected(self):
        secret = screenview.Element(
            3, screenview.ROLE_EDIT, "Password", "", 10, 10, 100, 30,
            protected=True,
        )
        with patch.object(module.screenview, "look", return_value=make_view([secret])), \
             patch.object(module.screenact, "type_text") as type_text:
            result = module.screen_perception(
                {"action": "type", "target": "Password", "text": "not-a-real-secret"}
            )
        self.assertIn("PROTECTED_FIELD", result)
        type_text.assert_not_called()

    def test_postcondition_is_explicitly_checked(self):
        el = screenview.Element(4, screenview.ROLE_BUTTON, "Open", "", 10, 10, 80, 30)
        before = make_view([el])
        after = make_view()
        after.contains_text = lambda value: value == "Dashboard"
        from core.screenact import Act
        with patch.object(module.screenview, "look", return_value=before), \
             patch.object(module.screenview, "wait_stable", return_value=after), \
             patch.object(module.screenact, "click", return_value=Act(True, "click")):
            result = module.screen_perception(
                {"action": "click", "target": "Open", "expect_text": "Dashboard"}
            )
        self.assertIn("ACTION_DELIVERED_AND_VERIFIED", result)

    def test_type_rejects_non_edit_controls(self):
        button = screenview.Element(5, screenview.ROLE_BUTTON, "Search", "", 10, 10, 80, 30)
        with patch.object(module.screenview, "look", return_value=make_view([button])), \
             patch.object(module.screenact, "type_text") as type_text:
            result = module.screen_perception(
                {"action": "type", "target": "Search", "text": "hello"}
            )
        self.assertIn("NOT_FOUND", result)
        type_text.assert_not_called()


if __name__ == "__main__":
    unittest.main()


class ScreenAuthorizationTests(unittest.TestCase):
    def test_inspection_is_read_only(self):
        from core.authorization import classify_action
        self.assertEqual(classify_action("screen_perception", {"action": "inspect"}), "read_only")

    def test_ordinary_desktop_controls_are_autonomous(self):
        from core.authorization import classify_action
        for params in (
            {"action": "click", "target": "Delete"},
            {"action": "click", "target": "Send"},
            {"action": "press", "key": "enter"},
            {"action": "type", "target": "Text Editor", "clear_first": True},
            {"action": "press", "key": "alt+f4"},
            {"action": "press", "key": "ctrl+s"},
            {"action": "press", "key": "ctrl+alt+delete"},
        ):
            with self.subTest(params=params):
                self.assertEqual(classify_action("screen_perception", params), "reversible_change")

    def test_purchase_and_checkout_controls_are_hard_blocked(self):
        from core.authorization import classify_action, decision_for
        for label in ("Buy now", "Checkout", "Pay now", "Finalizar compra", "Pagamento"):
            with self.subTest(label=label):
                action_class = classify_action(
                    "screen_perception", {"action": "click", "target": label}
                )
                self.assertEqual(action_class, "unknown_high_impact")
                self.assertEqual(decision_for(action_class), "deny")

    def test_inspect_reports_visual_fallback_when_accessibility_is_unavailable(self):
        view = make_view(degraded=True, source="ocr")
        with patch.object(module.screenview, "look", return_value=view):
            result = module.screen_perception({"action": "inspect"})
        self.assertIn("SCREEN_UNAVAILABLE", result)
        self.assertIn("accessibility tree is unavailable", result)

