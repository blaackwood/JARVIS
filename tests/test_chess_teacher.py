"""Tests for actions/chess_teacher.py (explanations, move grading, tool wiring).

The text logic runs on plain python-chess boards. Tests that need Stockfish are skipped
when the engine is not installed. No screen, voice or Jarvis window is used.
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import chess

from actions import chess_teacher as ct
from actions import chess_assistant as ca

_TEST_TMP = None
_TEST_PATCHES = []


def setUpModule():
    global _TEST_TMP, _TEST_PATCHES
    _TEST_TMP = tempfile.TemporaryDirectory(prefix="jarvis-test-chess-teacher-")
    root = Path(_TEST_TMP.name)
    teacher_dir = root / "chess_teacher"
    assistant_dir = root / "chess_assistant"
    _TEST_PATCHES = [
        patch.object(ct, "_DATA", teacher_dir),
        patch.object(ct, "_PROG", teacher_dir / "progresso.json"),
        patch.object(ct, "_CA_DATA", assistant_dir),
        patch.object(ct, "_CFG", assistant_dir / "config.json"),
        patch.object(ct, "_TPL", assistant_dir / "templates.npz"),
        patch.object(ca, "_DATA", assistant_dir),
        patch.object(ca, "_CFG", assistant_dir / "config.json"),
        patch.object(ca, "_TPL", assistant_dir / "templates.npz"),
    ]
    for item in _TEST_PATCHES:
        item.start()


def tearDownModule():
    for item in reversed(_TEST_PATCHES):
        item.stop()
    if _TEST_TMP is not None:
        _TEST_TMP.cleanup()


SF = ct._achar_stockfish()
needs_engine = unittest.skipUnless(SF, "Stockfish not installed")


def fake_infos(board, ucis, cps):
    out = []
    for u, cp in zip(ucis, cps):
        m = chess.Move.from_uci(u)
        out.append({"move": m, "score": chess.engine.PovScore(chess.engine.Cp(cp), board.turn).pov(board.turn),
                    "pv": [m]})
    return out


class Descricao(unittest.TestCase):
    def test_descrever_nao_altera_tabuleiro(self):
        b = chess.Board()
        fen = b.fen()
        self.assertEqual(ct.descrever(b, chess.Move.from_uci("g1f3")), "cavalo, g 1 para f 3")
        self.assertEqual(b.fen(), fen)

    def test_roque_e_xeque(self):
        b = chess.Board("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1")
        self.assertEqual(ct.descrever(b, chess.Move.from_uci("e1g1")), "roque pequeno")
        b = chess.Board("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1")
        self.assertIn("xeque-mate", ct.descrever(b, chess.Move.from_uci("a1a8")))

    def test_achar_lance(self):
        b = chess.Board()
        self.assertEqual(ct.achar_lance(b, "Nf3"), chess.Move.from_uci("g1f3"))
        self.assertEqual(ct.achar_lance(b, "g1 f3"), chess.Move.from_uci("g1f3"))
        self.assertEqual(ct.achar_lance(b, "e4"), chess.Move.from_uci("e2e4"))
        self.assertIsNone(ct.achar_lance(b, "e5"))
        self.assertIsNone(ct.achar_lance(b, ""))


class Motivos(unittest.TestCase):
    def txt(self, fen, uci, voce=True):
        b = chess.Board(fen)
        return " ".join(ct.motivos(b, chess.Move.from_uci(uci), voce))

    def test_peao_no_centro(self):
        self.assertIn("centro", self.txt(chess.STARTING_FEN, "e2e4"))

    def test_desenvolvimento(self):
        self.assertIn("Desenvolve", self.txt(chess.STARTING_FEN, "g1f3"))

    def test_mate(self):
        self.assertIn("xeque-mate", self.txt("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1", "a1a8"))

    def test_garfo(self):
        t = self.txt("2r5/5r2/8/1N6/8/8/8/K6k w - - 0 1", "b5d6")
        self.assertIn("garfo", t)

    def test_captura_de_graca(self):
        t = self.txt("rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2", "e4d5")
        self.assertIn("Captura", t)

    def test_roque(self):
        t = self.txt("r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1", "e1g1")
        self.assertIn("roque", t.lower())

    def test_lance_do_adversario_usa_terceira_pessoa(self):
        t = self.txt("2r5/5r2/8/1N6/8/8/8/K6k w - - 0 1", "b5d6", voce=False)
        self.assertIn("sua", t)
        self.assertNotIn("adversária", t)

    def test_sempre_devolve_algo(self):
        b = chess.Board()
        for m in b.legal_moves:
            self.assertTrue(ct.motivos(b, m))


class Explicacao(unittest.TestCase):
    def test_explicar_detalhado_e_curto(self):
        b = chess.Board()
        infos = fake_infos(b, ["e2e4", "d2d4", "a2a3"], [30, 25, -60])
        det = ct.explicar(b, infos, "detalhado")
        cur = ct.explicar(b, infos, "curto")
        self.assertTrue(det["frases"][0].startswith("A melhor jogada é"))
        self.assertGreater(len(det["frases"]), len(cur["frases"]))
        self.assertIn("quase tão boa", det["texto"])
        self.assertIn("pior", det["texto"])
        self.assertEqual(det["move"], chess.Move.from_uci("e2e4"))

    def test_aval(self):
        pov = lambda s: chess.engine.PovScore(s, chess.WHITE).pov(chess.WHITE)
        self.assertIn("equilibrada", ct._aval(pov(chess.engine.Cp(10))))
        self.assertIn("vantagem decisiva", ct._aval(pov(chess.engine.Cp(500))))
        self.assertIn("desvantagem", ct._aval(pov(chess.engine.Cp(-150))))
        self.assertIn("mate forçado em 3 para você", ct._aval(pov(chess.engine.Mate(3))))
        self.assertIn("adversário tem mate", ct._aval(pov(chess.engine.Mate(-2))))

    def test_avaliar_lance_classes(self):
        b = chess.Board()
        infos = fake_infos(b, ["e2e4", "d2d4"], [30, 25])
        ok = ct.avaliar_lance(lambda x: None, b, chess.Move.from_uci("e2e4"), infos)
        self.assertIn("Excelente", ok[0])
        quase = ct.avaliar_lance(lambda x: None, b, chess.Move.from_uci("d2d4"), infos)
        self.assertIn("praticamente", quase[0])
        pov = chess.engine.PovScore(chess.engine.Cp(-200), chess.WHITE).pov(chess.WHITE)
        erro = ct.avaliar_lance(lambda x: pov, b, chess.Move.from_uci("a2a3"), infos)
        self.assertIn("Erro", erro[0])
        self.assertIn("A melhor era", erro[1])
        pov = chess.engine.PovScore(chess.engine.Cp(-900), chess.WHITE).pov(chess.WHITE)
        grave = ct.avaliar_lance(lambda x: pov, b, chess.Move.from_uci("a2a3"), infos)
        self.assertIn("Erro grave", grave[0])

    def test_comentar_adversario(self):
        b = chess.Board()
        b.push_uci("e2e4")
        f = ct.comentar_lance(b, chess.Move.from_uci("e7e5"))
        self.assertTrue(f[0].startswith("O adversário jogou"))
        self.assertGreaterEqual(len(f), 2)


@needs_engine
class ComMotor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.motor = ct._Motor(SF)

    @classmethod
    def tearDownClass(cls):
        cls.motor.fechar()

    def test_analisar_e_explicar(self):
        b = chess.Board()
        infos = self.motor.analisar(b, 0.15, 3)
        self.assertEqual(len(infos), 3)
        res = ct.explicar(b, infos)
        self.assertTrue(res["frases"][0].startswith("A melhor jogada é"))
        self.assertIn(res["move"], b.legal_moves)

    def test_mate_em_um(self):
        b = chess.Board("6k1/5ppp/8/8/8/8/8/R3K3 w - - 0 1")
        infos = self.motor.analisar(b, 0.15, 3)
        res = ct.explicar(b, infos)
        self.assertIn("xeque-mate", res["texto"])

    def test_poucos_lances_legais(self):
        b = chess.Board("7k/8/5QK1/8/8/8/8/8 b - - 0 1")   # um unico lance legal (Kg8)
        infos = self.motor.analisar(b, 0.1, 3)
        self.assertEqual(len(infos), 1)

    def test_lance_fora_do_multipv_e_avaliado(self):
        b = chess.Board()
        infos = self.motor.analisar(b, 0.15, 3)
        r = ct.avaliar_lance(lambda x: self.motor.nota(x, 0.15, chess.WHITE), b, chess.Move.from_uci("f2f3"), infos)
        self.assertTrue(r)
        self.assertTrue(any(w in r[0] for w in ("Boa", "Imprecisão", "Erro")))


class Ferramenta(unittest.TestCase):
    def test_tool_valida(self):
        t = ct.TOOL
        self.assertTrue(re.match(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$", t["name"]))
        self.assertEqual(t["name"], "chess_teacher")
        self.assertTrue(callable(t["handler"]))
        self.assertEqual(t["parameters"]["type"], "OBJECT")
        acoes = t["parameters"]["properties"]["action"]["enum"]
        for a in ("start", "stop", "status", "explain", "explain_fen", "why", "repeat", "level", "calibrate"):
            self.assertIn(a, acoes)

    def test_nome_diferente_do_assistente(self):
        from actions import chess_assistant as ca
        self.assertNotEqual(ct.TOOL["name"], ca.TOOL["name"])
        self.assertIsNot(ct._S, ca._S)

    def test_acao_invalida_e_status(self):
        self.assertTrue(ct.chess_teacher({"action": "xyz"}).startswith("TEACHER_INVALID_ACTION"))
        self.assertTrue(ct.chess_teacher({"action": "status"}).startswith("TEACHER_"))
        self.assertTrue(ct.chess_teacher({"action": "why"}).startswith("TEACHER_NEEDS_MOVE"))
        self.assertTrue(ct.chess_teacher({"action": "stop"}).startswith("TEACHER_NOT_RUNNING"))
        self.assertTrue(ct.chess_teacher({"action": "explain_fen", "fen": "lixo"}).startswith(("TEACHER_INVALID_FEN", "STOCKFISH_NOT_FOUND")))

    @needs_engine
    def test_explain_fen_com_lance(self):
        r = ct.chess_teacher({"action": "explain_fen", "fen": chess.STARTING_FEN, "move": "e4", "think_time": 0.15})
        self.assertTrue(r.startswith("TEACHER_LESSON"), r)
        self.assertIn("Sobre peão, e 2 para e 4", r)
        r = ct.chess_teacher({"action": "explain_fen", "fen": chess.STARTING_FEN, "move": "e5"})
        self.assertTrue(r.startswith("TEACHER_INVALID_MOVE"), r)
        r = ct.chess_teacher({"action": "explain_fen", "fen": "8/8/8/8/8/8/8/8 w - - 0 1"})
        self.assertTrue(r.startswith("TEACHER_INVALID_POSITION"), r)

    def test_level(self):
        ct.chess_teacher({"action": "level", "level": "curto"})
        self.assertEqual(ct._S.nivel, "curto")
        ct.chess_teacher({"action": "level", "level": "detalhado"})
        self.assertEqual(ct._S.nivel, "detalhado")


class Voz(unittest.TestCase):
    def test_partir_frases_longas(self):
        longa = ("Captura a torre adversária em f 7, ganhando material, e a peça que captura fica fora de perigo; "
                 "além disso aumenta o controle das casas centrais do tabuleiro, de onde as peças alcançam os dois lados.")
        partes = ct._partir(longa)
        self.assertGreater(len(partes), 1)
        self.assertTrue(all(len(x) <= 170 for x in partes))
        self.assertEqual(" ".join(partes).replace("  ", " "), longa)
        self.assertEqual(ct._partir("Curta."), ["Curta."])
        self.assertEqual(ct._partir(""), [])

    def test_usa_voz_do_gemini_e_nao_so_sapi(self):
        import inspect
        src = inspect.getsource(ct._Fala)
        self.assertIn("speech_pcm", src)
        self.assertIn("get_voice", src)


class ProfessorIA(unittest.TestCase):
    def test_limpar_texto_tira_simbolos(self):
        sujo = "**Boa jogada!** Veja (isso) aqui: # um plano_bom `agora`."
        out = ct._limpar_texto(sujo)
        for ch_ in "*#`_()":
            self.assertNotIn(ch_, out)
        self.assertIn("Boa jogada!", out)

    def test_frases_de_divide_por_sentenca(self):
        self.assertEqual(ct._frases_de("Uma frase. Outra frase! E mais?"),
                         ["Uma frase.", "Outra frase!", "E mais?"])
        self.assertEqual(ct._frases_de(""), [])

    def test_fase_e_contexto(self):
        import chess
        b0 = chess.Board()
        self.assertEqual(ct._fase(b0), "abertura")
        self.assertEqual(ct._fase(chess.Board("8/5k2/8/8/8/3K4/4P3/8 w - - 0 40")), "final")
        ctx = ct._contexto(b0, True, ["Boa!"], ["A melhor jogada é x."], "curto")
        self.assertEqual(ctx["cor"], "brancas")
        self.assertEqual(ctx["pre"], ["Boa!"])
        self.assertEqual(ctx["nivel"], "curto")

    def test_falar_aula_cai_nas_frases_prontas_se_llm_falha(self):
        import time
        f = ct._Fala.__new__(ct._Fala)
        f.q = ct.queue.Queue()
        f.gen = 0
        f._parar_som = lambda: None
        antigo = ct._aula_llm
        ct._aula_llm = lambda ctx, timeout_ms=9000: None
        try:
            f.falar_aula(["Frase pronta."], {"fen": "x", "lance": 1, "fase": "abertura",
                                              "cor": "brancas", "nivel": "curto", "pre": [], "fatos": ["a"]})
            item = f.q.get(timeout=3)
        finally:
            ct._aula_llm = antigo
        self.assertEqual(item[1], "Frase pronta.")

    def test_falar_aula_usa_texto_do_professor(self):
        f = ct._Fala.__new__(ct._Fala)
        f.q = ct.queue.Queue()
        f.gen = 0
        f._parar_som = lambda: None
        antigo, guardar = ct._aula_llm, ct._guardar
        ct._aula_llm = lambda ctx, timeout_ms=9000: "Primeira ideia. Segunda ideia."
        ct._guardar = lambda frases: None
        try:
            f.falar_aula(["Frase pronta."], {"fen": "x"})
            a = f.q.get(timeout=3)
            b = f.q.get(timeout=3)
        finally:
            ct._aula_llm, ct._guardar = antigo, guardar
        self.assertEqual([a[1], b[1]], ["Primeira ideia.", "Segunda ideia."])


class ProgressoErros(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmp = tempfile.mkdtemp()
        self._old = (ct._DATA, ct._PROG)
        ct._DATA = ct.Path(self._tmp)
        ct._PROG = ct._DATA / "progresso.json"

    def tearDown(self):
        import shutil
        ct._DATA, ct._PROG = self._old
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_tema_por_palavra_chave(self):
        self.assertEqual(ct._tema("Dá xeque ao rei"), "xeques")
        self.assertEqual(ct._tema("Cria um garfo no cavalo"), "garfos")
        self.assertEqual(ct._tema("algo sem relacao"), "outros")

    def test_registrar_e_persistir(self):
        self.assertEqual(ct.registrar_lance("abertura", 10, ""), 0)
        self.assertEqual(ct.registrar_lance("meio-jogo", 200, "capturas"), 1)
        self.assertEqual(ct.registrar_lance("meio-jogo", 90, "capturas"), 2)
        d = ct._prog_ler()
        self.assertEqual((d["lances"], d["erros"]), (3, 2))
        self.assertEqual(d["temas"], {"capturas": 2})
        self.assertEqual(d["por_fase"]["meio-jogo"], [2, 2])
        self.assertTrue(ct._PROG.exists())

    def test_perfil_so_com_dados_suficientes(self):
        self.assertEqual(ct.perfil_texto(), "")
        for _ in range(6):
            ct.registrar_lance("meio-jogo", 200, "segurança do rei")
        for _ in range(4):
            ct.registrar_lance("abertura", 0, "")
        txt = ct.perfil_texto()
        self.assertIn("meio-jogo", txt)
        self.assertIn("segurança do rei", txt)

    def test_registrar_avisa_padrao_recorrente(self):
        import chess
        sai = {"perda": 200, "tema": "capturas"}
        b = chess.Board()
        self.assertEqual(ct._registrar(b, sai), [])
        self.assertEqual(ct._registrar(b, sai), [])
        aviso = ct._registrar(b, sai)
        self.assertEqual(len(aviso), 1)
        self.assertIn("capturas", aviso[0])
        self.assertEqual(ct._registrar(b, {}), [])

    def test_avaliar_lance_preenche_saida(self):
        import chess
        import chess.engine as eng
        b = chess.Board()
        infos = [{"move": chess.Move.from_uci("e2e4"), "score": eng.Cp(50), "pv": []}]
        sai = {}
        ct.avaliar_lance(lambda b2: eng.Cp(-100), b, chess.Move.from_uci("a2a3"), infos, sai)
        self.assertEqual(sai["perda"], 150)
        self.assertIn("tema", sai)
        sai2 = {}
        ct.avaliar_lance(lambda b2: eng.Cp(0), b, chess.Move.from_uci("e2e4"), infos, sai2)
        self.assertEqual(sai2["perda"], 0)

    def test_acao_progress(self):
        self.assertTrue(ct.chess_teacher({"action": "progress"}).startswith("TEACHER_PROGRESS_EMPTY"))
        ct.registrar_lance("abertura", 200, "xeques")
        self.assertTrue(ct.chess_teacher({"action": "progress"}).startswith("TEACHER_PROGRESS:"))


if __name__ == "__main__":
    unittest.main()
