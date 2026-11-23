import unittest
from unittest.mock import Mock, patch

from core import guidance, screenview
from core.guidance import GuidanceTarget, point_inside, wait_for_user_click, wait_for_user_hover
from actions import highlight_screen_target as highlight_module
from actions import wait_for_guidance_click as wait_module


class FakeClock:
    def __init__(self):
        self.value=0.0
    def __call__(self):
        return self.value
    def sleep(self, seconds):
        self.value += max(0.001,float(seconds))


class GuidanceGeometryTests(unittest.TestCase):
    def test_point_inside_uses_exact_rectangle_edges(self):
        rect=(100,200,80,40)
        self.assertTrue(point_inside(rect,(100,200)))
        self.assertTrue(point_inside(rect,(180,240)))
        self.assertTrue(point_inside(rect,(140,220)))
        self.assertFalse(point_inside(rect,(99,200)))
        self.assertFalse(point_inside(rect,(181,240)))

    def test_wait_ignores_outside_click_and_advances_only_on_new_inside_click(self):
        target=GuidanceTarget((100,100,80,80),"Save","app","title",22,2,0.0)
        states=iter([
            {"down":False,"x":0,"y":0},       # initial button state
            {"down":True,"x":20,"y":20},      # outside press
            {"down":False,"x":20,"y":20},     # release
            {"down":True,"x":120,"y":120},    # valid new press
        ])
        clock=FakeClock()
        result=wait_for_user_click(
            target,timeout=2,poll=lambda:next(states, {"down":False,"x":120,"y":120}),
            clock=clock,sleep=clock.sleep,interval=0.001,
        )
        self.assertEqual(result["status"],"clicked")
        self.assertEqual(result["target"],"Save")
        self.assertEqual(result["point"],[120,120])

    def test_button_already_held_at_wait_start_is_not_counted(self):
        target=GuidanceTarget((10,10,80,80),"OK","app","title",1,1,0.0)
        states=iter([
            {"down":True,"x":20,"y":20},  # button held before wait begins
            {"down":True,"x":20,"y":20},
            {"down":False,"x":20,"y":20},
            {"down":True,"x":20,"y":20},
        ])
        clock=FakeClock()
        result=wait_for_user_click(target,timeout=1,poll=lambda:next(states, {"down":False,"x":20,"y":20}),
                                   clock=clock,sleep=clock.sleep,interval=0.001)
        self.assertEqual(result["status"],"clicked")

    def test_escape_cancels_without_waiting_for_click(self):
        target=GuidanceTarget((10,10,80,80),"OK","app","title",1,1,0.0)
        result=wait_for_user_click(target,timeout=10,poll=lambda:{"down":False},
                                   cancel=lambda:True)
        self.assertEqual(result["status"],"cancelled")

    def test_hover_requires_a_fresh_entry_and_stable_dwell(self):
        target=GuidanceTarget((100,100,80,80),"Settings","app","title",22,2,0.0)
        states=iter([
            {"down":False,"x":20,"y":20},    # initially outside
            {"down":False,"x":120,"y":120},  # enter target
            {"down":False,"x":120,"y":120},  # dwell
            {"down":False,"x":20,"y":20},    # leave: reset dwell
            {"down":False,"x":120,"y":120},  # enter afresh
            {"down":False,"x":120,"y":120},
            {"down":False,"x":120,"y":120},
            {"down":False,"x":120,"y":120},
            {"down":False,"x":120,"y":120},
        ])
        clock=FakeClock()
        result=wait_for_user_hover(
            target,timeout=2,poll=lambda:next(states, {"down":False,"x":120,"y":120}),
            dwell=0.03,clock=clock,sleep=clock.sleep,interval=0.01,
        )
        self.assertEqual(result["status"],"hovered")
        self.assertEqual(result["target"],"Settings")
        self.assertGreaterEqual(result["dwell"],0.03)

    def test_hover_ignores_pointer_while_mouse_button_is_down(self):
        target=GuidanceTarget((10,10,80,80),"Menu","app","title",1,1,0.0)
        states=iter([
            {"down":True,"x":20,"y":20},    # held at wait start
            {"down":True,"x":20,"y":20},
            {"down":False,"x":0,"y":0},     # release outside
            {"down":False,"x":20,"y":20},   # fresh hover begins
            {"down":False,"x":20,"y":20},
            {"down":False,"x":20,"y":20},
        ])
        clock=FakeClock()
        result=wait_for_user_hover(
            target,timeout=1,poll=lambda:next(states, {"down":False,"x":20,"y":20}),
            dwell=0.02,clock=clock,sleep=clock.sleep,interval=0.01,
        )
        self.assertEqual(result["status"],"hovered")

    def test_hover_timeout_does_not_advance(self):
        target=GuidanceTarget((10,10,80,80),"Menu","app","title",1,1,0.0)
        clock=FakeClock()
        result=wait_for_user_hover(
            target,timeout=0.05,
            poll=lambda:{"down":False,"x":0,"y":0},
            clock=clock,sleep=clock.sleep,interval=0.01,
        )
        self.assertEqual(result["status"],"timeout")

    def test_timeout_stays_on_same_target(self):
        target=GuidanceTarget((10,10,80,80),"OK","app","title",1,1,0.0)
        clock=FakeClock()
        result=wait_for_user_click(target,timeout=0.05,
                                   poll=lambda:{"down":False,"x":20,"y":20},
                                   clock=clock,sleep=clock.sleep,interval=0.01)
        self.assertEqual(result["status"],"timeout")


def make_view(elements, *, app="target.exe", title="Target app", pid=42,
              degraded=False, source="uia"):
    return screenview.View(
        source=source,degraded=degraded,app=app,title=title,pid=pid,
        elements=list(elements),digest="fresh",stable_digest="fresh",
    )


class GuidedScreenActionTests(unittest.TestCase):
    def setUp(self):
        guidance.clear_target()
        self.player=Mock()

    def tearDown(self):
        guidance.clear_target()

    def test_highlight_uses_exact_unique_uia_bounds(self):
        element=screenview.Element(1,screenview.ROLE_BUTTON,"Save","",100,120,90,34)
        view=make_view([element])
        with patch.object(highlight_module.screenview,"look",return_value=view):
            result=highlight_module.highlight_screen_target(
                {"target":"Save","step":3},player=self.player
            )
        self.assertIn("TARGET_HIGHLIGHTED",result)
        target=guidance.get_target()
        self.assertEqual(target.rect,(100,120,90,34))
        self.assertEqual(target.step,3)
        self.player.show_guidance_target.assert_called_once_with((100,120,90,34),"Save",3)

    def test_highlight_refuses_ocr_and_degraded_views(self):
        element=screenview.Element(1,screenview.ROLE_BUTTON,"Save","",10,10,50,30)
        for view in (
            make_view([element],degraded=True,source="ocr"),
            make_view([element],degraded=True,source="uia"),
        ):
            with patch.object(highlight_module.screenview,"look",return_value=view):
                result=highlight_module.highlight_screen_target({"target":"Save"},player=self.player)
            self.assertIn("SCREEN_UNAVAILABLE",result)
        self.player.show_guidance_target.assert_not_called()

    def test_highlight_refuses_duplicate_exact_controls(self):
        a=screenview.Element(1,screenview.ROLE_BUTTON,"Save","",10,10,50,30)
        b=screenview.Element(2,screenview.ROLE_BUTTON,"Save","",100,10,50,30)
        with patch.object(highlight_module.screenview,"look",return_value=make_view([a,b])):
            result=highlight_module.highlight_screen_target({"target":"Save"},player=self.player)
        self.assertIn("AMBIGUOUS_TARGET",result)
        self.player.show_guidance_target.assert_not_called()

    def test_wait_refuses_missing_or_changed_target_window(self):
        guidance.set_target((10,10,50,30),"Save",app="target.exe",title="Target app",pid=42)
        changed=make_view([],app="other.exe",title="Other app",pid=55)
        with patch.object(wait_module.screenview,"look",return_value=changed):
            result=wait_module.wait_for_guidance_click({},player=self.player)
        self.assertIn("TARGET_WINDOW_CHANGED",result)
        self.player.clear_guidance_target.assert_called_once()

    def test_wait_action_supports_real_hover_mode(self):
        element=screenview.Element(1,screenview.ROLE_BUTTON,"Settings","",100,120,90,34)
        guidance.set_target(element.rect,"Settings",app="target.exe",title="Target app",pid=42)
        with patch.object(wait_module.screenview,"look",return_value=make_view([element])):
            with patch.object(wait_module,"wait_for_user_hover",
                              return_value={"status":"hovered","dwell":0.45,"point":[120,130]}):
                result=wait_module.wait_for_guidance_click(
                    {"mode":"hover","timeout":3},player=self.player
                )
        self.assertIn("GUIDANCE_HOVERED",result)
        self.assertIsNone(guidance.get_target())

    def test_wait_reports_verified_visible_postcondition(self):
        element=screenview.Element(1,screenview.ROLE_BUTTON,"Save","",100,120,90,34)
        before=make_view([element])
        dashboard=screenview.Element(2,screenview.ROLE_TEXT,"Dashboard","",20,20,180,40)
        after=make_view([dashboard])
        guidance.set_target((100,120,90,34),"Save",app="target.exe",title="Target app",pid=42)
        states=iter([
            {"down":False,"x":0,"y":0},
            {"down":True,"x":120,"y":130},
        ])
        with patch.object(wait_module.screenview,"look",side_effect=[before,after]), \
             patch.object(wait_module,"windows_mouse_poll",side_effect=lambda:next(states)), \
             patch.object(wait_module,"windows_escape_down",return_value=False):
            result=wait_module.wait_for_guidance_click(
                {"timeout":3,"expect_text":"Dashboard"},player=self.player
            )
        self.assertIn("CLICK_AND_POSTCONDITION_VERIFIED",result)
        self.assertIsNone(guidance.get_target())
        self.player.clear_guidance_target.assert_called_once()

    def test_wait_refreshes_highlight_when_live_control_moved_before_wait(self):
        old=screenview.Element(1,screenview.ROLE_BUTTON,"Save","",100,120,90,34)
        moved=screenview.Element(1,screenview.ROLE_BUTTON,"Save","",300,220,90,34)
        before=make_view([old])
        current=make_view([moved])
        states=iter([
            {"down":False,"x":0,"y":0},
            {"down":True,"x":320,"y":230},
        ])
        guidance.set_target(old.rect,"Save",app="target.exe",title="Target app",pid=42,role=old.role)
        with patch.object(wait_module.screenview,"look",side_effect=[current,current]), \
             patch.object(wait_module,"windows_mouse_poll",side_effect=lambda:next(states)), \
             patch.object(wait_module,"windows_escape_down",return_value=False):
            result=wait_module.wait_for_guidance_click({"timeout":3},player=self.player)
        self.assertIn("CLICK_SEEN_NOT_VERIFIED",result)
        self.player.show_guidance_target.assert_called_once_with(moved.rect,"Save",1)

    def test_wait_rejects_click_inside_old_frame_after_control_moves_again(self):
        old=screenview.Element(1,screenview.ROLE_BUTTON,"Save","",100,120,90,34)
        moved=screenview.Element(1,screenview.ROLE_BUTTON,"Save","",300,220,90,34)
        before=make_view([old])
        after=make_view([moved])
        guidance.set_target(old.rect,"Save",app="target.exe",title="Target app",pid=42,role=old.role)
        states=iter([
            {"down":False,"x":0,"y":0},
            {"down":True,"x":120,"y":130},
        ])
        with patch.object(wait_module.screenview,"look",side_effect=[before,after]), \
             patch.object(wait_module,"windows_mouse_poll",side_effect=lambda:next(states)), \
             patch.object(wait_module,"windows_escape_down",return_value=False):
            result=wait_module.wait_for_guidance_click({"timeout":3},player=self.player)
        self.assertIn("CLICK_TARGET_MOVED",result)

    def test_wait_does_not_claim_success_without_postcondition(self):
        element=screenview.Element(1,screenview.ROLE_BUTTON,"Save","",100,120,90,34)
        before=make_view([element])
        after=make_view([element])
        guidance.set_target((100,120,90,34),"Save",app="target.exe",title="Target app",pid=42)
        states=iter([
            {"down":False,"x":0,"y":0},
            {"down":True,"x":120,"y":130},
        ])
        with patch.object(wait_module.screenview,"look",side_effect=[before,after]), \
             patch.object(wait_module,"windows_mouse_poll",side_effect=lambda:next(states)), \
             patch.object(wait_module,"windows_escape_down",return_value=False):
            result=wait_module.wait_for_guidance_click({"timeout":3},player=self.player)
        self.assertIn("CLICK_SEEN_NOT_VERIFIED",result)
        self.assertNotIn("CLICK_AND_POSTCONDITION_VERIFIED",result)

    def test_action_classification_matches_guidance_side_effects(self):
        from core.authorization import classify_action
        self.assertEqual(classify_action("highlight_screen_target",{}),"reversible_change")
        self.assertEqual(classify_action("wait_for_guidance_click",{}),"read_only")


class GuidanceOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_overlay_tracks_logical_target_and_passes_mouse_through(self):
        from PyQt6.QtCore import Qt
        from gui.screen_marks import DesktopGuidanceOverlay
        overlay=DesktopGuidanceOverlay()
        try:
            overlay.show_target((120,140,90,36),"Save",2)
            self.app.processEvents()
            self.assertTrue(overlay.isVisible())
            self.assertEqual(overlay._target.width(),90)
            self.assertEqual(overlay._target.height(),36)
            self.assertEqual(overlay._label,"Save")
            self.assertEqual(overlay._step,2)
            self.assertTrue(overlay.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents))
            overlay.clear_target()
            self.app.processEvents()
            self.assertFalse(overlay.isVisible())
        finally:
            overlay.close()


if __name__=="__main__":
    unittest.main()
