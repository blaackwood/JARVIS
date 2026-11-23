"""Tests for JARVIS language preference, translation and speech locale."""
import unittest
from unittest import mock

from core import i18n
from memory import config_manager


class AppLanguageConfigTests(unittest.TestCase):
    def test_clean_install_defaults_to_english(self):
        with mock.patch.object(config_manager, "load_api_keys", return_value={}):
            self.assertEqual(config_manager.get_app_language(), "en-US")

    def test_saved_portuguese_preference_is_preserved(self):
        with mock.patch.object(
            config_manager, "load_api_keys", return_value={"app_language": "pt-BR"}
        ):
            self.assertEqual(config_manager.get_app_language(), "pt-BR")

    def test_normalization_handles_common_locale_aliases(self):
        self.assertEqual(config_manager.normalize_app_language("en"), "en-US")
        self.assertEqual(config_manager.normalize_app_language("English"), "en-US")
        self.assertEqual(config_manager.normalize_app_language("pt_BR"), "pt-BR")
        self.assertEqual(config_manager.normalize_app_language("Português"), "pt-BR")
        self.assertEqual(config_manager.normalize_app_language("unknown"), "en-US")

    def test_save_validates_and_persists_only_supported_locale(self):
        with mock.patch.object(config_manager, "_patch_config") as patch_config:
            config_manager.save_app_language("pt-BR")
            patch_config.assert_called_once_with(app_language="pt-BR")
            config_manager.save_app_language("en-US")
            self.assertEqual(patch_config.call_count, 2)
            with self.assertRaises(ValueError):
                config_manager.save_app_language("fr-FR")


class AppLanguageRuntimeTests(unittest.TestCase):
    def test_selector_offers_english_first_and_pt_br(self):
        self.assertEqual(i18n.LANGUAGE_CHOICES[0], ("English (US)", "en-US"))
        self.assertIn(("Português (Brasil)", "pt-BR"), i18n.LANGUAGE_CHOICES)

    def test_hud_labels_translate_in_both_directions(self):
        self.assertEqual(i18n.tr("INÍCIO", "en-US"), "HOME")
        self.assertEqual(i18n.tr("HOME", "pt-BR"), "INÍCIO")
        self.assertEqual(i18n.tr("Microfone", "en-US"), "Microphone")
        self.assertEqual(i18n.tr("Remote access", "pt-BR"), "Acesso remoto")
        self.assertEqual(i18n.tr("TASKS", "pt-BR"), "TAREFAS")
        self.assertEqual(i18n.tr("MODULES", "en-US"), "MODULES")
        self.assertEqual(i18n.tr("MUDO", "en-US"), "MUTED")
        self.assertEqual(i18n.tr("Interromper", "en-US"), "Interrupt")
        self.assertEqual(i18n.tr("Tela cheia", "en-US"), "Full screen")
        self.assertEqual(i18n.tr("1-4 estados  N noticias  S pesquisa  H inicio  T tarefas  R rotinas  C controles  G config  M mutar  I interromper  O esfera  Espaco demo  F11 tela cheia  Esc sair", "en-US"), "1-4 states  N news  S search  H home  T tasks  R routines  C controls  G settings  M mute  I interrupt  O orb  Space demo  F11 full screen  Esc exit")

    def test_hud_labels_stay_in_the_selected_language(self):
        self.assertEqual(i18n.tr("MODULE", "pt-BR"), "M\u00d3DULO")
        self.assertEqual(i18n.tr("OVERVIEW", "pt-BR"), "VIS\u00c3O GERAL")
        self.assertEqual(
            i18n.tr("JARVIS SYSTEMS  \u00b7  DESKTOP", "pt-BR"),
            "JARVIS  \u00b7  SISTEMA DESKTOP",
        )
        self.assertEqual(i18n.tr("Configura\u00e7\u00f5es do Jarvis", "en-US"), "JARVIS settings")
        self.assertEqual(i18n.tr("PR\u00d3XIMA  \u2192", "en-US"), "NEXT  \u2192")
        self.assertEqual(i18n.tr("Testing\u2026", "pt-BR"), "Testando\u2026")
        self.assertEqual(i18n.tr("SAVE SETTINGS", "pt-BR"), "SALVAR CONFIGURA\u00c7\u00d5ES")
        self.assertEqual(i18n.tr("Expected answer: ", "pt-BR"), "Resposta esperada: ")
        self.assertEqual(
            i18n.tr("Leave blank to keep the currently saved key. Secret values are never displayed.", "pt-BR"),
            "Deixe em branco para manter a chave salva. Valores secretos nunca são exibidos.",
        )
        self.assertEqual(
            i18n.tr("Quick assistant controls (click to toggle)", "pt-BR"),
            "Controles rápidos do assistente (clique para alternar)",
        )
        self.assertEqual(i18n.tr("Tarefa: relat?rio", "en-US"), "Task: relat?rio")
        self.assertEqual(i18n.tr("Esfera: holograma", "en-US"), "Orb: hologram")
        self.assertEqual(i18n.tr("Task: report", "pt-BR"), "Tarefa: report")

    def test_language_name_and_speech_locale_follow_selection(self):
        self.assertEqual(i18n.language_name("en-US"), "English (United States, en-US)")
        self.assertEqual(i18n.speech_language_code("en-US"), "en-US")
        self.assertEqual(i18n.speech_language_code("pt-BR"), "pt-BR")

    def test_visual_content_instruction_is_strict_and_locale_specific(self):
        english = i18n.visual_content_instruction("en-US")
        portuguese = i18n.visual_content_instruction("pt-BR")
        self.assertIn("American English", english)
        self.assertIn("3D object/part labels", english)
        self.assertIn("Do not leave Portuguese words", english)
        self.assertIn("Brazilian Portuguese", portuguese)
        self.assertIn("3D object/part labels", portuguese)
        self.assertIn("Do not leave English words", portuguese)
        self.assertNotIn("Brazilian Portuguese", english)
        self.assertNotIn("American English", portuguese)

    def test_visual_tool_declarations_include_selected_language_policy(self):
        from core.action_loader import ActionRecord, ActionRegistry
        records = {
            "show_visual": ActionRecord(
                name="show_visual", description="base visual tool", parameters={}, valid=True
            ),
            "present_visual_lesson": ActionRecord(
                name="present_visual_lesson", description="base lesson tool", parameters={}, valid=True
            ),
        }
        registry = ActionRegistry(records, lambda _message: None)
        with mock.patch.object(config_manager, "load_api_keys", return_value={"app_language": "en-US"}):
            en = registry.get_tool_declarations()
        with mock.patch.object(config_manager, "load_api_keys", return_value={"app_language": "pt-BR"}):
            pt = registry.get_tool_declarations()
        for declaration in en:
            self.assertIn("VISUAL CONTENT LANGUAGE — HARD REQUIREMENT", declaration["description"])
            self.assertIn("American English", declaration["description"])
            self.assertIn("Do not leave Portuguese words", declaration["description"])
        for declaration in pt:
            self.assertIn("VISUAL CONTENT LANGUAGE — HARD REQUIREMENT", declaration["description"])
            self.assertIn("Brazilian Portuguese", declaration["description"])
            self.assertIn("Do not leave English words", declaration["description"])

    def test_startup_greeting_matches_selected_locale(self):
        english = i18n.startup_greeting_prompt(8, "en-US")
        portuguese = i18n.startup_greeting_prompt(20, "pt-BR")
        self.assertIn("Good morning sir", english)
        self.assertIn("Boa noite, senhor", portuguese)

    def test_final_language_instruction_matches_selected_locale(self):
        english = i18n.language_instruction("en-US")
        portuguese = i18n.language_instruction("pt-BR")
        self.assertIn("American English", english)
        self.assertIn("Brazilian Portuguese", portuguese)
        self.assertNotIn("Brazilian Portuguese", english)
        self.assertNotIn("American English", portuguese)
        self.assertIn("\n", english)
        self.assertIn("\n", portuguese)


if __name__ == "__main__":
    unittest.main()
