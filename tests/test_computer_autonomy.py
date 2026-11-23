import unittest

from actions import browser_control, computer_control
from core.authorization import classify_action, decision_for


class ComputerAutonomyTests(unittest.TestCase):
    def test_jarvis_minimize_action_is_registered(self):
        self.assertIn("minimize_jarvis", computer_control.TOOL["parameters"]["properties"]["action"]["description"])

    def test_browser_video_actions_are_autonomous(self):
        action_class = classify_action("browser_control", {
            "action": "smart_click", "description": "first video"
        })
        self.assertEqual(action_class, "reversible_change")
        self.assertEqual(decision_for(action_class), "allow")

    def test_browser_purchase_intent_is_denied(self):
        for action, field, value in (
            ("smart_click", "description", "Buy now"),
            ("click", "text", "Checkout"),
            ("go_to", "url", "https://shop.example/checkout"),
            ("search", "query", "how to purchase an item"),
        ):
            with self.subTest(action=action, value=value):
                action_class = classify_action("browser_control", {
                    "action": action, field: value
                })
                self.assertEqual(action_class, "unknown_high_impact")
                self.assertEqual(decision_for(action_class), "deny")

    def test_browser_purchase_guard_recognizes_portuguese_and_english(self):
        for label in ("Buy now", "Checkout", "Pay now", "Finalizar compra",
                      "Adicionar ao carrinho", "Pagamento"):
            with self.subTest(label=label):
                self.assertTrue(browser_control._purchase_blocked(label))

    def test_browser_purchase_guard_does_not_block_video_selection(self):
        self.assertFalse(browser_control._purchase_blocked("Play first video"))
        self.assertFalse(browser_control._purchase_blocked("Open YouTube results"))


if __name__ == "__main__":
    unittest.main()
