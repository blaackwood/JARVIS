import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "_jarvis_agent_ui"))

import codex_agent


class CodexWebQualityPolicyTests(unittest.TestCase):
    def test_web_creation_requests_activate_web_workflow(self):
        self.assertTrue(codex_agent._is_web_frontend_task("Crie um site de estudos com dashboard responsivo."))

    def test_frontend_refactor_requests_activate_web_workflow(self):
        self.assertTrue(codex_agent._is_web_frontend_task("Reformule o visual do menu e das telas do frontend."))

    def test_html_css_attachment_activates_web_workflow(self):
        self.assertTrue(codex_agent._is_web_frontend_task("Melhore a interface", [("index.html", ""), ("styles.css", "")]))

    def test_non_web_requests_do_not_activate_web_workflow(self):
        self.assertFalse(codex_agent._is_web_frontend_task("Explique a diferença entre razão e proporção."))

    def test_web_effort_prefers_high_for_practical_speed(self):
        model = {"supportedReasoningEfforts": [
            {"reasoningEffort": "low"}, {"reasoningEffort": "medium"},
            {"reasoningEffort": "high"}, {"reasoningEffort": "xhigh"},
            {"reasoningEffort": "max"},
        ], "defaultReasoningEffort": "medium"}
        self.assertEqual(codex_agent._select_reasoning_effort(model, web_task=True), "high")

    def test_web_effort_falls_back_to_xhigh_when_high_is_unavailable(self):
        model = {"supportedReasoningEfforts": [
            {"reasoningEffort": "low"}, {"reasoningEffort": "medium"},
            {"reasoningEffort": "xhigh"}, {"reasoningEffort": "max"}, {"reasoningEffort": "ultra"},
        ]}
        self.assertEqual(codex_agent._select_reasoning_effort(model, web_task=True), "xhigh")

    def test_non_web_tasks_keep_model_default_effort(self):
        model = {"supportedReasoningEfforts": [
            {"reasoningEffort": "low"}, {"reasoningEffort": "medium"},
            {"reasoningEffort": "high"}, {"reasoningEffort": "max"},
        ], "defaultReasoningEffort": "medium"}
        self.assertEqual(codex_agent._select_reasoning_effort(model, web_task=False), "medium")

    def test_effort_falls_back_to_supported_option(self):
        model = {"supportedReasoningEfforts": [{"reasoningEffort": "medium"}],
                 "defaultReasoningEffort": "high"}
        self.assertEqual(codex_agent._select_reasoning_effort(model, web_task=True), "medium")

    def test_web_workflow_directive_requires_first_pass_quality(self):
        directive = codex_agent._web_workflow_directive()
        self.assertIn("PADRÃO DA PRIMEIRA ENTREGA", directive)
        self.assertIn("REVISÃO AUTÔNOMA OBRIGATÓRIA", directive)
        self.assertIn("três problemas mais importantes", directive)

    def test_web_workflow_directive_reuses_preferred_reference(self):
        directive = codex_agent._web_workflow_directive()
        self.assertIn("versões que o usuário já escolheu ou elogiou", directive)
        self.assertIn("não peça ao usuário para repeti-las", directive)

    def test_hallmark_is_included_in_web_skill_inputs(self):
        items = codex_agent._web_skill_inputs()
        hallmark = next((item for item in items if item["name"] == "hallmark"), None)
        self.assertIsNotNone(hallmark)
        self.assertTrue(Path(hallmark["path"]).is_file())

    def test_hallmark_directive_includes_theme_lint_and_network_guardrails(self):
        directive = codex_agent._web_workflow_directive()
        self.assertIn("$hallmark", directive)
        self.assertIn("sloplint.mjs --render", directive)
        self.assertIn("não execute theme.mjs photos", directive)
        self.assertIn("HIERARQUIA DE REGRAS", directive)
        self.assertIn("quatro perguntas padrão", directive.lower())

    def test_web_workflow_directive_contains_real_line_breaks(self):
        directive = codex_agent._web_workflow_directive()
        self.assertIn("\n", directive)
        self.assertNotIn("\\n", directive)
        self.assertIn("$webapp-testing", directive)
        self.assertIn("jarvis_browser_qa.py", directive)
        self.assertIn("--project-dir", directive)

    def test_required_skill_inputs_are_added_only_for_web_tasks(self):
        items = codex_agent._web_skill_inputs()
        names = {item["name"] for item in items}
        self.assertIn("hallmark", names)
        self.assertIn("frontend-design", names)
        self.assertIn("webapp-testing", names)
        self.assertNotIn("jarvis-web-workflow", names)
        self.assertTrue(all(Path(item["path"]).is_file() for item in items))


if __name__ == "__main__":
    unittest.main()
