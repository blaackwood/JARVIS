import io
import unittest
from unittest.mock import patch

from PIL import Image

from core.molecule import parse_smiles, layout_molecule
from core.visual_board import normalize_visual_payload

def model_scene(label="Cena", x=2, y=3):
    """Fixture de cena 3D válida: cinco corpos rotulados e conexões entre eles."""
    names = ("Núcleo", "Entrada", "Processo", "Saída", "Energia")
    offsets = ((0, 0, 0), (-28, -12, 0), (28, -12, 2), (-16, 25, 5), (18, 26, -4))
    shapes = ("sphere", "cube", "cylinder", "cone", "torus")
    parts = [
        {
            "id": f"part-{i}",
            "shape": shapes[i],
            "size": 18 if i == 0 else 10 + i,
            "dx": offsets[i][0],
            "dy": offsets[i][1],
            "dz": offsets[i][2],
            "label": f"{label} {names[i]}",
        }
        for i in range(5)
    ]
    return {
        "type": "model3d",
        "x": x,
        "y": y,
        "width": 62,
        "height": 88,
        "shape": "none",
        "parts": parts,
        "links": [
            {"from": "part-0", "to": f"part-{i}", "flow": True}
            for i in range(1, 5)
        ],
    }



class MoleculeParserTests(unittest.TestCase):
    def test_simple_chain_and_double_bond(self):
        atoms,bonds=parse_smiles("CCO")
        self.assertEqual([a["element"] for a in atoms],["C","C","O"])
        self.assertEqual([(b["a"],b["b"],b["order"]) for b in bonds],
                         [(0,1,1.0),(1,2,1.0)])
        atoms,bonds=parse_smiles("O=C=O")
        self.assertEqual([b["order"] for b in bonds],[2.0,2.0])

    def test_branching_and_ring_closures(self):
        atoms,bonds=parse_smiles("CC(O)C")
        self.assertEqual(len(atoms),4)
        self.assertEqual(len(bonds),3)
        atoms,bonds=parse_smiles("C1=CC=CC=C1")
        self.assertEqual(len(atoms),6)
        self.assertEqual(len(bonds),6)
        self.assertEqual(sum(1 for b in bonds if b["order"]==2),3)

    def test_aromatic_bonds_and_bracket_charge(self):
        atoms,bonds=parse_smiles("c1cc[nH]cc1")
        self.assertTrue(all(a["aromatic"] for a in atoms))
        self.assertEqual(len(bonds),6)
        atoms,bonds=parse_smiles("[NH4+]")
        self.assertEqual(atoms[0]["element"],"N")
        self.assertEqual(atoms[0]["charge"],1)

    def test_rejects_incomplete_or_unsupported_smiles(self):
        for value in ("", "C1CC", "C(", "C)", "C/C", "Xx"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    parse_smiles(value)

    def test_layout_is_bounded_and_deterministic(self):
        atoms,bonds=parse_smiles("CC(=O)O")
        one=layout_molecule(atoms,bonds)
        two=layout_molecule(atoms,bonds)
        self.assertEqual(one,two)
        self.assertTrue(all(0<=a["x"]<=100 and 0<=a["y"]<=100 for a in one))


class RichVisualPayloadTests(unittest.TestCase):
    def test_photo_map_and_molecule_payloads_normalize(self):
        payload=normalize_visual_payload({
            "title":"Science",
            "elements":[
                {"id":"photo-1","type":"photo","query":"Water","caption":"Water"},
                {"id":"map-1","type":"map","region":"Europe",
                 "pins":[
                     {"name":"Lisbon","lat":38.7223,"lon":-9.1393},
                     {"name":"Madrid","lat":40.4168,"lon":-3.7038},
                 ],
                 "routes":[{"from":"Lisbon","to":"Madrid","label":"Route"}]},
                {"id":"mol-1","type":"molecule","smiles":"CCO"},
            ],
        })
        self.assertEqual([x["type"] for x in payload["elements"]],["photo","map","model3d"])  # molecules are 3D ball-and-stick
        self.assertEqual(payload["elements"][0]["photo_query"],"Water")
        self.assertEqual(len(payload["elements"][1]["pins"]),2)
        self.assertEqual(len(payload["elements"][1]["routes"]),1)
        self.assertEqual(len(payload["elements"][2]["atoms"]),3)
        self.assertEqual(len(payload["elements"][2]["bonds"]),2)
        self.assertEqual(len(payload["elements"][2]["parts"]),3)
        self.assertEqual(len(payload["elements"][2]["links"]),2)

    def test_invalid_map_routes_are_dropped_and_coordinates_clamped(self):
        payload=normalize_visual_payload({
            "elements":[{
                "type":"map",
                "pins":[{"name":"A","lat":120,"lon":-300},{"name":"B","lat":0,"lon":0}],
                "routes":[{"from":"A","to":"Missing"},{"from":"A","to":"B"}],
            }]
        })
        item=payload["elements"][0]
        self.assertEqual(item["pins"][0]["lat"],90)
        self.assertEqual(item["pins"][0]["lon"],-180)
        self.assertEqual(len(item["routes"]),1)
        self.assertEqual(item["routes"][0]["to"],"B")

    def test_molecule_without_atoms_is_rejected(self):
        with self.assertRaises(ValueError):
            normalize_visual_payload({"elements":[{"type":"molecule"}]})


class PhotoAssetTests(unittest.TestCase):
    def test_wikipedia_photo_fetch_uses_validated_redirects_and_limits(self):
        import core.visual_assets as assets
        png=io.BytesIO()
        Image.new("RGB",(20,20),(10,80,120)).save(png,format="PNG")
        image_bytes=png.getvalue()
        summary=b'{"title":"Water","thumbnail":{"source":"https://upload.wikimedia.org/water.png"}}'
        with patch.object(assets,"_get_public",side_effect=[
            (summary,"application/json","https://en.wikipedia.org/api/rest_v1/page/summary/Water"),
            (image_bytes,"image/png","https://upload.wikimedia.org/water.png"),
        ]) as get:
            assets._fetch_query.cache_clear()
            assets._fetch_image.cache_clear()
            photo=assets.fetch_photo(query="Water")
        self.assertEqual(photo["title"],"Water")
        self.assertEqual(photo["mime_type"],"image/png")
        self.assertEqual(photo["data"],image_bytes)
        self.assertEqual(get.call_count,2)

    def test_edit_visual_reloads_photo_bytes_for_an_in_place_photo_update(self):
        from unittest.mock import Mock
        from actions.edit_visual import edit_visual
        player=Mock()
        with patch("core.visual_assets.fetch_photo",return_value={
            "data":b"PNG-UPDATED","mime_type":"image/png",
            "title":"Water","credit":"Wikipedia"
        }):
            result=edit_visual({
                "operation":"update",
                "element_id":"photo-1",
                "element":{"type":"photo","query":"Water","caption":"New caption"}
            },player=player)
        self.assertIn("VISUAL_EDITED",result)
        args=player.edit_visual_board.call_args.args
        self.assertEqual(args[0],"update")
        self.assertEqual(args[1],"photo-1")
        self.assertEqual(args[2]["photo_data"],b"PNG-UPDATED")
        self.assertEqual(args[2]["caption"],"New caption")

    def test_edit_visual_reloads_photo_bytes_for_an_in_place_photo_update(self):
        from unittest.mock import Mock
        from actions.edit_visual import edit_visual
        player=Mock()
        with patch("core.visual_assets.fetch_photo",return_value={
            "data":b"PNG-UPDATED","mime_type":"image/png",
            "title":"Water","credit":"Wikipedia"
        }):
            result=edit_visual({
                "operation":"update",
                "element_id":"photo-1",
                "element":{"type":"photo","query":"Water","caption":"New caption"}
            },player=player)
        self.assertIn("VISUAL_EDITED",result)
        args=player.edit_visual_board.call_args.args
        self.assertEqual(args[0],"update")
        self.assertEqual(args[1],"photo-1")
        self.assertEqual(args[2]["photo_data"],b"PNG-UPDATED")
        self.assertEqual(args[2]["caption"],"New caption")

    def test_photo_without_query_or_url_is_rejected(self):
        from core.visual_assets import fetch_photo
        with self.assertRaises(ValueError):
            fetch_photo()

    def test_embedded_url_credentials_are_refused_before_network(self):
        import core.visual_assets as assets
        with patch.object(assets,"_get_public") as get:
            with self.assertRaisesRegex(ValueError,"credentials"):
                assets.fetch_photo(url="https://user:pass@example.com/photo.png")
        get.assert_not_called()

    def test_show_visual_injects_photo_bytes_and_degrades_on_missing_image(self):
        from unittest.mock import Mock
        from actions.visual_board import show_visual
        player=Mock()
        with patch("core.visual_assets.fetch_photo",return_value={
            "data":b"\\x89PNG", "mime_type":"image/png",
            "title":"Water","credit":"Wikipedia"
        }):
            result=show_visual({
                "title":"Photo",
                "elements":[model_scene("Água"), {"type":"photo","query":"Water"}]
            },player=player)
        self.assertIn("VISUAL_SHOWN",result)
        sent=next(item for item in player.show_visual_board.call_args.args[0]["elements"] if item["type"] == "photo")
        self.assertEqual(sent["photo_data"],b"\\x89PNG")
        self.assertEqual(sent["credit"],"Wikipedia")

        player.reset_mock()
        with patch("core.visual_assets.fetch_photo",side_effect=RuntimeError("no image")):
            result=show_visual({
                "title":"Fallback",
                "elements":[model_scene("Fallback"), {"type":"photo","query":"Unknown Thing"}]
            },player=player)
        self.assertIn("VISUAL_SHOWN",result)
        sent=next(item for item in player.show_visual_board.call_args.args[0]["elements"] if item["type"] == "photo")
        self.assertIn("Imagem indisponível",sent["photo_error"])


class RichVisualRenderingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_model3d_primitives_render_as_lit_solid_meshes(self):
        from PyQt6.QtCore import QRectF, Qt
        from PyQt6.QtGui import QColor, QImage, QPainter
        from gui.visual_rich import draw_rich_element, _solid_mesh

        for shape in ("cube", "sphere", "cylinder", "cone", "torus"):
            with self.subTest(shape=shape):
                image = QImage(500, 360, QImage.Format.Format_ARGB32_Premultiplied)
                image.fill(Qt.GlobalColor.transparent)
                painter = QPainter(image)
                draw_rich_element(painter, QRectF(0, 0, 500, 360), {
                    "type": "model3d", "x": 50, "y": 50,
                    "width": 55, "height": 65, "shape": shape,
                    "render_style": "solid", "title": shape.title(),
                }, QColor(87, 224, 255), phase=0.63)
                painter.end()
                visible = []
                tones = set()
                for y in range(70, 330):
                    for x in range(100, 420):
                        px = image.pixelColor(x, y)
                        if px.alpha() > 150:
                            visible.append((x, y))
                            tones.add((px.red(), px.green(), px.blue()))
                self.assertGreater(len(visible), 250, f"{shape} did not produce a visible solid surface")
                self.assertGreater(len(tones), 6, f"{shape} has no visible face-lighting variation")
                self.assertGreater(len(_solid_mesh(shape)), 10)

    def test_model3d_moving_parts_and_wireframe_remain_supported(self):
        from PyQt6.QtCore import QRectF, Qt
        from PyQt6.QtGui import QColor, QImage, QPainter
        from gui.visual_rich import draw_rich_element
        from core.visual_board import normalize_visual_payload

        solid = normalize_visual_payload({"elements": [{
            "type": "model3d", "shape": "cylinder", "render_style": "solid",
            "parts": [{"shape": "sphere", "dx": 12, "dy": 0, "size": 10,
                       "motion": "orbit", "speed": 1.5}],
        }]})["elements"][0]
        self.assertEqual(solid["render_style"], "solid")
        self.assertEqual(solid["parts"][0]["render_style"], "solid")

        image = QImage(400, 280, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        draw_rich_element(painter, QRectF(0, 0, 400, 280), solid,
                          QColor(185, 139, 255), phase=1.7)
        wire = dict(solid, render_style="wireframe", shape="cube")
        draw_rich_element(painter, QRectF(0, 0, 400, 280), wire,
                          QColor(87, 224, 255), phase=1.7)
        painter.end()
        self.assertGreater(
            sum(1 for y in range(image.height()) for x in range(image.width())
                if image.pixelColor(x, y).alpha() > 120),
            250,
        )

    def test_photo_map_and_molecule_render_to_qimage(self):
        from PyQt6.QtCore import QRectF,Qt
        from PyQt6.QtGui import QColor,QImage,QPainter
        from gui.visual_rich import draw_rich_element
        png=io.BytesIO()
        Image.new("RGB",(30,20),(30,120,160)).save(png,format="PNG")
        items=[
            {"id":"p","type":"photo","x":5,"y":5,"width":28,"height":40,
             "title":"Photo","caption":"Caption","photo_data":png.getvalue()},
            {"id":"map","type":"map","x":36,"y":5,"width":28,"height":40,
             "title":"Places","pins":[
                 {"name":"Lisbon","lat":38.7,"lon":-9.1},
                 {"name":"Madrid","lat":40.4,"lon":-3.7}],
              "routes":[{"from":"Lisbon","to":"Madrid"}]},
            {"id":"mol","type":"molecule","x":67,"y":5,"width":28,"height":40,
             "title":"Ethanol","atoms":[
                 {"element":"C","x":20,"y":50},{"element":"C","x":50,"y":50},{"element":"O","x":80,"y":50}],
              "bonds":[{"a":0,"b":1,"order":1},{"a":1,"b":2,"order":1}]},
        ]
        image=QImage(1000,600,QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.GlobalColor.transparent)
        painter=QPainter(image)
        for item in items:
            draw_rich_element(painter,QRectF(0,0,1000,600),item,QColor(87,224,255))
        painter.end()
        self.assertGreater(image.pixelColor(500,100).alpha(),0)
        self.assertGreater(image.pixelColor(100,100).alpha(),0)
        self.assertGreater(image.pixelColor(760,100).alpha(),0)


if __name__=="__main__":
    unittest.main()
