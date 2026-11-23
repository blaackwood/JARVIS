"""Vision-assisted exam extraction using cloud models only.

Gemini is the preferred model. When its quota is exhausted, the Lab tries
the configured remote vision provider and the existing Gemini cloud ladder.
No local language or vision model is started. Every crop remains pending
human approval.
"""
from __future__ import annotations

import html
import json
import re
import statistics
import threading
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path

from PIL import Image
from core import gemini

MAX_PAGES = 32
MAX_SIDE = 2400
MAX_SOURCE_BYTES = 50 * 1024 * 1024
# The first attempt is pinned to a known model. Only a quota error activates
# the configured remote vision provider and the shared cloud model ladder.
EXAM_CLOUD_MODEL = "gemini-3.1-flash-lite"
_EXAM_CLOUD_LOCK = threading.Lock()
_EXAM_CLOUD_LAST_CALL = 0.0
_EXAM_CLOUD_MIN_INTERVAL = 4.2  # conservative spacing for free-tier RPM limits


def _parse_json(text):
    raw = re.sub(r"^\x60{3}(?:json)?\s*|\s*\x60{3}$", "", str(text or "").strip(), flags=re.I)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Vision model did not return valid JSON.")
    data = json.loads(raw[start:end + 1])
    if not isinstance(data, dict):
        raise ValueError("Response is not a JSON object.")
    return data


def _box_pixels(box, width, height):
    if not isinstance(box, (list, tuple)) or len(box) != 4:
        raise ValueError("Bounding box must contain x0,y0,x1,y1.")
    v = [float(x) for x in box]
    if not all(0 <= x <= 1000 for x in v):
        raise ValueError("Coordinates must be normalized from 0 to 1000.")
    x0, y0, x1, y1 = v
    if x1 <= x0 or y1 <= y0:
        raise ValueError("Bounding box has invalid area.")
    px = (int(x0 * width / 1000), int(y0 * height / 1000),
          min(width, int(x1 * width / 1000)), min(height, int(y1 * height / 1000)))
    if px[2] <= px[0] or px[3] <= px[1]:
        raise ValueError("Bounding box is too small at this image resolution.")
    return px


def _configured_cloud_vision_provider() -> str:
    """Return the configured coding/sidecar provider only when it is remote and vision-capable."""
    try:
        from memory.config_manager import get_provider_config, get_providers

        settings = get_providers()
        candidates = [
            str(settings.get("coding") or "").strip(),
            str(settings.get("sidecar") or "").strip(),
        ]
        for provider_id in candidates:
            if not provider_id:
                continue
            cfg = get_provider_config(provider_id)
            base_url = str(cfg.get("base_url") or "").strip().lower()
            model = str(cfg.get("model") or "").strip().lower()
            vision_flag = str(cfg.get("vision") or "").strip().lower() in {
                "1", "true", "yes", "on"
            }
            vision_model = bool(re.search(r"(?:^|[-_/])(?:vl|vision)(?:[-_/]|$)", model))
            if base_url.startswith("https://") and (vision_flag or vision_model):
                return provider_id
    except Exception as exc:
        print(f"[ExamLab] cloud vision provider discovery failed: {type(exc).__name__}")
    return ""


def _exam_cloud_call(contents, timeout_ms=90000):
    """Use pinned Gemini first; on quota exhaustion, use configured cloud vision providers."""
    global _EXAM_CLOUD_LAST_CALL
    primary_error = None
    try:
        with _EXAM_CLOUD_LOCK:
            wait = _EXAM_CLOUD_MIN_INTERVAL - (time.monotonic() - _EXAM_CLOUD_LAST_CALL)
            if wait > 0:
                time.sleep(wait)
            api_key = gemini.api_key()
            if not api_key:
                raise RuntimeError("No Google Gemini API key is configured.")
            client = gemini.client(timeout_ms=timeout_ms, key=api_key, retry_attempts=1)
            _EXAM_CLOUD_LAST_CALL = time.monotonic()
            return client.models.generate_content(model=EXAM_CLOUD_MODEL, contents=contents)
    except Exception as exc:
        if not _is_cloud_quota_error(exc):
            raise
        primary_error = exc

    provider_id = _configured_cloud_vision_provider()
    if not provider_id:
        raise RuntimeError(
            "Google Gemini quota exceeded and no configured remote vision provider is available."
        ) from primary_error

    print(f"[ExamLab] Gemini quota exhausted; trying configured cloud vision provider {provider_id}.")
    response = gemini.call(
        contents,
        tier=gemini.SMART,
        timeout_ms=timeout_ms,
        provider=provider_id,
    )
    if response is None or not (getattr(response, "text", None) or "").strip():
        raise RuntimeError(
            "Google Gemini quota exceeded; the configured cloud vision provider and Gemini cloud ladder "
            "did not return a usable response. The page remains pending for a later cloud retry."
        ) from primary_error
    return response



def _is_cloud_quota_error(exc):
    """Recognize hard quota/rate-limit errors, not transient server overloads."""
    message = str(exc).lower()
    return any(token in message for token in (
        "429", "resource_exhausted", "quota exceeded", "quota_exceeded",
        "rate limit", "ratelimitexceeded", "requests_per_day",
        "daily limit", "per day limit",
    ))



def _tighten_overlapping_boxes(boxes, width, height):
    """Trim intersecting question crops at the midpoint between their centers."""
    adjusted = {idx: list(box) for idx, box in boxes.items()}
    keys = list(adjusted)
    for pos, left_id in enumerate(keys):
        for right_id in keys[pos + 1:]:
            a, b = adjusted[left_id], adjusted[right_id]
            if not _overlap(a, b):
                continue
            acx, acy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
            bcx, bcy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            dx, dy = abs(acx - bcx) / max(1, width), abs(acy - bcy) / max(1, height)
            if dx >= dy and abs(acx - bcx) >= 12:
                cut = int((acx + bcx) / 2)
                if acx < bcx:
                    a[2] = min(a[2], cut)
                    b[0] = max(b[0], cut)
                else:
                    b[2] = min(b[2], cut)
                    a[0] = max(a[0], cut)
            elif abs(acy - bcy) >= 12:
                cut = int((acy + bcy) / 2)
                if acy < bcy:
                    a[3] = min(a[3], cut)
                    b[1] = max(b[1], cut)
                else:
                    b[3] = min(b[3], cut)
                    a[1] = max(a[1], cut)
    for idx, box in adjusted.items():
        x0, y0, x1, y1 = box
        if x1 - x0 < 80 or y1 - y0 < 45:
            adjusted[idx] = list(boxes[idx])
    return adjusted


def _analyze_page(image, page_number):
    from google.genai import types
    img = image.copy().convert("RGB")
    if max(img.size) > MAX_SIDE:
        img.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=90)
    part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
    prompt = (
        f"Analise a pagina {page_number} de uma prova. Detecte cada questao visivel. "
        "Para cada questao, delimite um retangulo JUSTO, rente ao conteudo: numero, enunciado inteiro e todas as alternativas. "
        "Nao deixe margens grandes, nao capture nenhuma linha, alternativa ou figura de outra questao. "
        "Se duas questoes estiverem lado a lado, respeite rigorosamente a coluna de cada uma. "
        "Inclua figuras apenas quando elas pertencerem exclusivamente a questao. "
        "Nao corte conteudo e nao inclua questoes vizinhas. Coordenadas normalizadas 0..1000 "
        "na ordem [x0,y0,x1,y1], origem no canto superior esquerdo. "
        "Detecte TAMBEM blocos de contexto compartilhado: texto-base/passagem, tirinha, charge, "
        "figura, grafico, tabela, mapa ou imagem que uma ou mais questoes usam. "
        "Para cada bloco compartilhado, informe bbox, tipo, id, notas e os numeros das questoes "
        "que dependem dele em applies_to_numbers. Se o cabecalho indicar um intervalo como "
        "questoes 01 a 08, inclua TODOS os numeros desse intervalo mesmo quando parte das "
        "questoes estiver em paginas seguintes; informe tambem applies_to_range [inicio,fim]. "
        "Nao duplique o bloco dentro de cada questao. "
        "Se uma questao mencionar texto, tirinha, quadrinho, figura, grafico ou tabela, verifique "
        "se o material de referencia esta dentro do recorte; se estiver fora, crie um bloco compartilhado. "
        "Se continuar na pagina seguinte, marque continues_next_page=true e needs_review=true. "
        "Se houver duvida, confidence baixo e needs_review=true. Retorne SOMENTE JSON: "
        '{"questions":[{"number":"01","text":"enunciado","alternatives":["A..."],'
        '"bbox":[0,0,1000,500],"confidence":0.0,"continues_next_page":false,'
        '"needs_review":false,"notes":""}],"shared_contexts":['
        '{"id":"passage_01_08","kind":"shared_passage","applies_to_numbers":["01","02"],'
        '"applies_to_range":[1,8],"bbox":[0,0,500,700],"confidence":0.0,"notes":""}]}'
    )
    response = _exam_cloud_call([prompt, part], timeout_ms=90000)
    if response is None or not getattr(response, "text", None):
        raise RuntimeError("No configured vision model returned a result.")
    data = _parse_json(response.text)
    if not isinstance(data.get("questions"), list):
        raise ValueError("Gemini response has no questions list.")
    return data, img




def _repair_missing_boxes(image, page_number, questions):
    """Ask the pinned cloud model to locate questions whose first bbox was invalid."""
    from google.genai import types
    buf = BytesIO()
    image.convert("RGB").save(buf, format="JPEG", quality=90)
    part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
    candidates = [
        {"index": i, "number": str(q.get("number", i)),
         "text": str(q.get("text", ""))[:900],
         "alternatives": q.get("alternatives", [])[:8]}
        for i, q in questions
    ]
    prompt = (
        f"Revisor de coordenadas da pagina {page_number} de uma prova. "
        "A imagem e a pagina inteira. Para cada questao listada, localize um retangulo "
        "que inclua numero, enunciado completo e TODAS as alternativas. Inclua grafico, "
        "tabela ou figura exclusiva da questao. Se houver texto-base/figura compartilhada, "
        "nao precisa inclui-lo no retangulo se estiver separado como contexto. "
        "Coordenadas normalizadas 0..1000 [x0,y0,x1,y1], origem no canto superior esquerdo. "
        "Nao omita questoes. Retorne somente JSON: "
        '{"boxes":[{"index":1,"bbox":[0,0,1000,500],"notes":"..."}]}\n'
        + json.dumps(candidates, ensure_ascii=False)
    )
    response = _exam_cloud_call([prompt, part], timeout_ms=45000)
    if response is None or not getattr(response, "text", None):
        raise RuntimeError("Cloud bbox repair returned an empty response.")
    parsed = _parse_json(response.text)
    rows = parsed.get("boxes")
    if not isinstance(rows, list):
        raise ValueError("Cloud bbox repair returned no boxes list.")
    repaired = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            idx = int(row.get("index"))
            _box_pixels(row.get("bbox"), image.width, image.height)
        except (TypeError, ValueError):
            continue
        repaired[idx] = list(row.get("bbox"))
    return repaired


def _cloud_second_review(folder, page_number, questions):
    """Gemini cloud reviews every crop together with its linked shared context."""
    from google.genai import types
    reviews = {}
    for idx, q in enumerate(questions, 1):
        parts = []
        for rel in [q["crop_image"], *(q.get("context_images") or [])]:
            with Image.open(folder / rel) as source:
                buf = BytesIO()
                source.convert("RGB").save(buf, format="JPEG", quality=92)
            parts.append(types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg"))
        prompt = (
            f"Segundo revisor de prova, pagina {page_number}, questao {q.get('number', idx)}. "
            "A primeira imagem e o recorte da questao. As imagens seguintes sao textos-base, "
            "figuras, tabelas ou contextos compartilhados associados. Avalie tudo em conjunto. "
            "Confirme se numero, enunciado e TODAS as alternativas estao completos. Se a questao "
            "depende de material compartilhado, confirme que ele esta anexado e legivel. "
            "Nao aprove se faltar qualquer parte essencial. Na duvida, uncertain. "
            "A transcricao abaixo e apenas uma pista; priorize as imagens. "
            + json.dumps({"text": q.get("text", ""), "alternatives": q.get("alternatives", [])},
                         ensure_ascii=False)[:2200]
            + '\nRetorne somente JSON: {"verdict":"complete|needs_attention|uncertain",'
              '"issues":["problema objetivo"],"notes":"observacao curta"}'
        )
        response=_exam_cloud_call([prompt, *parts], timeout_ms=45000)
        if response is None or not getattr(response, "text", None):
            return None
        try:
            data=_parse_json(response.text)
        except Exception:
            return None
        verdict=str(data.get("verdict", "uncertain")).lower().strip()
        if verdict not in {"complete","needs_attention","uncertain"}:
            verdict="uncertain"
        issues=data.get("issues", [])
        reviews[idx]={
            "provider":"Gemini cloud / segunda leitura por quest?o",
            "status":verdict,
            "issues":[str(x)[:300] for x in issues[:8]] if isinstance(issues,list) else [],
            "notes":str(data.get("notes",""))[:500],
            "context_assets_sent":len(parts)-1,
        }
    return reviews


def _render_pdf(path):
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(path))
    try:
        if len(doc) < 1:
            raise ValueError("PDF has no pages.")
        if len(doc) > MAX_PAGES:
            raise ValueError(f"First version supports up to {MAX_PAGES} pages per batch. Split the PDF.")
        pages = []
        for i in range(len(doc)):
            im = doc[i].render(scale=2.0).to_pil().convert("RGB")
            if max(im.size) > MAX_SIDE:
                im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
            pages.append(im)
        return pages
    finally:
        doc.close()



def _pdf_text_question_regions(path):
    """
    Extrai limites de questões e alternativas A-E usando a camada textual do PDF.
    O resultado é por página e coluna; páginas escaneadas sem texto retornam lista vazia.
    """
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(path))
    result = {}
    try:
        for page_index in range(len(doc)):
            page = doc[page_index]
            width, height = page.get_size()
            textpage = page.get_textpage()
            chars = []
            for char_index in range(textpage.count_chars()):
                ch = textpage.get_text_range(char_index, 1)
                if ch in ("\r", "\n"):
                    continue
                left, bottom, right, top = textpage.get_charbox(char_index)
                chars.append((height - top, (left + right) / 2, left, ch,
                              height - bottom, right))
            if len(chars) < 80:
                result[page_index + 1] = []
                continue

            centers = sorted(row[1] for row in chars)
            gaps = [
                (b - a, (a + b) / 2)
                for a, b in zip(centers, centers[1:])
                if 0.25 * width < a and b < 0.75 * width
            ]
            widest_gap = max(gaps, default=(0.0, width / 2))
            left_count = sum(x < width / 2 for x in centers)
            right_count = len(centers) - left_count
            two_columns = (
                widest_gap[0] >= 5.5
                and left_count >= max(80, int(0.10 * len(centers)))
                # A sparse right-hand "RASCUNHO" strip is still a separate column.
                and right_count >= 20
            )
            if two_columns:
                split_x = widest_gap[1]
                columns = [
                    ("L", [row for row in chars if row[1] < split_x], 0.0, split_x),
                    ("R", [row for row in chars if row[1] >= split_x], split_x, width),
                ]
            else:
                columns = [("A", chars, 0.0, width)]

            page_regions = []
            for column_name, column_chars, column_min, column_max in columns:
                if len(column_chars) < 80:
                    continue
                # Character left edges establish the true text margin for this column.
                text_margin = min(row[2] for row in column_chars)
                ordered = sorted(column_chars, key=lambda row: (row[0], row[2]))
                groups = []
                for y, center_x, x, ch, y_bottom, x_right in ordered:
                    group = next(
                        (g for g in reversed(groups[-8:]) if abs(g["y"] - y) < 2.8),
                        None,
                    )
                    if group is None:
                        groups.append({"y": y, "bottom": y_bottom,
                                       "items": [(x, ch, x_right)]})
                    else:
                        group["items"].append((x, ch, x_right))
                        group["bottom"] = max(group["bottom"], y_bottom)

                lines = []
                for group in groups:
                    items = sorted(group["items"], key=lambda item: item[0])
                    line_text = "".join(item[1] for item in items).strip()
                    if not line_text:
                        continue
                    lines.append({
                        "y0": group["y"],
                        "y1": group["bottom"],
                        "x0": min(item[0] for item in items),
                        "x1": max(item[2] for item in items),
                        "text": line_text,
                    })

                candidates = []
                for line_index, line in enumerate(lines):
                    match = re.match(
                        r"^(\d{1,3})\.? (?=[A-Za-zÀ-ÖØ-öø-ÿ])".replace(" ", r"\s*"),
                        line["text"],
                    )
                    # Question numbers align with the left edge of their column.
                    # This excludes numbers embedded in a question, dates and data.
                    if match and line["x0"] - text_margin <= 8:
                        number = int(match.group(1))
                        if 1 <= number <= 200:
                            candidates.append((line_index, number, line))

                for candidate_index, (line_index, number, start_line) in enumerate(candidates):
                    next_index = (
                        candidates[candidate_index + 1][0]
                        if candidate_index + 1 < len(candidates)
                        else len(lines)
                    )
                    block = lines[line_index:next_index]
                    alternative_positions = {}
                    for local_index, line in enumerate(block):
                        marker = re.match(r"^\(([A-E])\)\s*", line["text"])
                        if marker and marker.group(1) not in alternative_positions:
                            alternative_positions[marker.group(1)] = (local_index, line)

                    if set(alternative_positions) != set("ABCDE"):
                        continue

                    # Include short wrapped continuations after alternative E, but never
                    # include the page footer/candidate code as part of the question.
                    e_index, e_line = alternative_positions["E"]
                    last_index = e_index
                    end_y = e_line["y1"]
                    for local_index in range(e_index + 1, len(block)):
                        line = block[local_index]
                        lowered = line["text"].casefold()
                        compact = re.sub(r"[^a-z0-9]", "", lowered)
                        if any(token in compact for token in (
                            "confidencialate", "pmes2601", "rascunho",
                            "nomedocandidato", "inscricao",
                        )):
                            break
                        if line["y0"] - end_y > 15:
                            break
                        if line["x0"] <= text_margin + 8:
                            break
                        last_index = local_index
                        end_y = max(end_y, line["y1"])

                    content_lines = block[:last_index + 1]
                    footer_detected = any(
                        "confidencial" in row["text"].casefold()
                        for row in block
                    )
                    alt_rows = []
                    for letter in "ABCDE":
                        alt_index, alt_line = alternative_positions[letter]
                        following = next(
                            (alternative_positions[next_letter][0]
                             for next_letter in "ABCDE"
                             if letter < next_letter and next_letter in alternative_positions),
                            len(content_lines),
                        )
                        pieces = []
                        for row in content_lines[alt_index:following]:
                            text = row["text"]
                            if row is alt_line:
                                text = re.sub(r"^\([A-E]\)\s*", "", text, count=1)
                            text = re.sub(r"(?i)confidencial.*$", "", text).strip()
                            if text:
                                pieces.append(text)
                        alt_rows.append("(" + letter + ") " + " ".join(pieces).strip())

                    prompt_lines = []
                    for row in content_lines[:alternative_positions["A"][0]]:
                        text = row["text"].strip()
                        if text:
                            prompt_lines.append(text)
                    prompt = " ".join(prompt_lines).strip()
                    # Build geometry from the complete question block, including all
                    # prompt/alternative lines and short wrapped continuations.
                    x0 = max(column_min, min(row["x0"] for row in content_lines) - 3.0)
                    x1 = min(column_max, max(row["x1"] for row in content_lines) + 3.0)
                    y0 = max(0.0, start_line["y0"] - 3.0)
                    y1 = min(height, end_y + 3.0)
                    page_regions.append({
                        "number": f"{number:02d}",
                        "page": page_index + 1,
                        "page_width": width,
                        "page_height": height,
                        "column": column_name,
                        "column_x0": column_min,
                        "column_x1": column_max,
                        "bbox_points": [x0, y0, x1, y1],
                        "prompt": prompt,
                        "alternatives": alt_rows,
                        "options_found": list("ABCDE"),
                        "footer_detected": footer_detected,
                    })
            result[page_index + 1] = page_regions
    finally:
        doc.close()
    return result


def _question_number_key(value):
    raw = str(value or "").strip()
    if raw.isdigit():
        number = int(raw)
        return f"{number:02d}" if number < 100 else str(number)
    return ""


def _reconcile_page_questions(raw_questions, regions, image_width, image_height, warnings, page_no):
    """
    Replaces model rectangles with PDF-text geometry when all A-E alternatives are
    independently present. Adds missing questions found in the PDF text layer.
    """
    if not regions:
        for question in raw_questions:
            if isinstance(question, dict):
                question.setdefault("flags", []).append(
                    "A camada textual do PDF nao permitiu verificar todas as alternativas; revisao visual obrigatoria."
                )
                question["geometry_check"] = {
                    "status": "unverified",
                    "reason": "no complete A-E block found in PDF text layer",
                }
        return raw_questions

    by_number = {region["number"]: region for region in regions}
    output = []
    seen = set()
    for question in raw_questions:
        if not isinstance(question, dict):
            continue
        number = _question_number_key(question.get("number"))
        if not number:
            if str(question.get("number", "")).strip().casefold() in ("redação", "redacao", "essay"):
                warnings.append(
                    f"Page {page_no}: essay/cover material was kept out of the objective-question list."
                )
                continue
            question.setdefault("flags", []).append(
                "Item sem numero objetivo; conferir e classificar manualmente."
            )
            output.append(question)
            continue
        region = by_number.get(number)
        if region is None:
            question.setdefault("flags", []).append(
                "Numero nao reconciliado com cinco alternativas A-E no texto do PDF; revisao manual obrigatoria."
            )
            question["geometry_check"] = {"status": "unverified"}
            output.append(question)
            continue
        if number in seen:
            warnings.append(f"Page {page_no}: duplicate model detection for question {number} was discarded.")
            continue
        seen.add(number)

        sx = image_width / max(1.0, region["page_width"])
        sy = image_height / max(1.0, region["page_height"])
        px0, py0, px1, py1 = region["bbox_points"]
        geo_box = (
            max(0, int(px0 * sx)),
            max(0, int(py0 * sy)),
            min(image_width, int(px1 * sx + 0.999)),
            min(image_height, int(py1 * sy + 0.999)),
        )
        col_left = max(0, int(region["column_x0"] * sx))
        col_right = min(image_width, int(region["column_x1"] * sx + 0.999))
        final_box = list(geo_box)
        footer_in_region = bool(region.get("footer_detected")) or any(
            "confidencial" in str(x).casefold()
            for x in region.get("alternatives", [])
        )
        try:
            model_box = _box_pixels(question.get("bbox"), image_width, image_height)
            clipped = (
                max(col_left, model_box[0]),
                max(geo_box[1], model_box[1]),
                min(col_right, model_box[2]),
                min(geo_box[3], model_box[3]),
            )
            if clipped[2] > clipped[0] and clipped[3] > clipped[1] and not footer_in_region:
                final_box = [
                    min(geo_box[0], clipped[0]),
                    min(geo_box[1], clipped[1]),
                    max(geo_box[2], clipped[2]),
                    max(geo_box[3], clipped[3]),
                ]
        except Exception:
            pass

        question["number"] = number
        # Preserve the vision model's readable OCR when it already supplied a
        # complete question. The PDF text layer is authoritative for geometry
        # and A-E detection, but its character stream may omit spaces/hyphenation.
        if not str(question.get("text", "")).strip() and region["prompt"]:
            question["text"] = region["prompt"]
        existing_alts = question.get("alternatives")
        if not isinstance(existing_alts, list) or len(existing_alts) != 5:
            question["alternatives"] = region["alternatives"]
        # The centered VUNESP footer can overlap the final E line in PDF text
        # coordinates. Keep it out of the question crop.
        if footer_in_region:
            final_box[3] = max(final_box[1] + 20, final_box[3] - int(25 * sy))
        question["bbox"] = [
            final_box[0] * 1000 / image_width,
            final_box[1] * 1000 / image_height,
            final_box[2] * 1000 / image_width,
            final_box[3] * 1000 / image_height,
        ]
        question["flags"] = [
            flag for flag in (question.get("flags") or [])
            if flag not in (
                "Recorte muito pequeno",
                "Recorte parece uniforme ou em branco",
                "Baixo contraste aparente",
            )
        ]
        question["geometry_check"] = {
            "status": "verified",
            "source": "pdfium_text_layer",
            "alternatives_detected": ["A", "B", "C", "D", "E"],
            "bbox_basis": "question_prompt_through_option_E",
        }
        question["notes"] = (
            str(question.get("notes", "")).strip() + " "
            "Retangulo reconciliado com a camada textual do PDF; A-E localizadas. "
            "A conferencia visual continua obrigatoria."
        ).strip()
        output.append(question)

    for number, region in sorted(by_number.items(), key=lambda item: int(item[0])):
        if number in seen:
            continue
        sx = image_width / max(1.0, region["page_width"])
        sy = image_height / max(1.0, region["page_height"])
        px0, py0, px1, py1 = region["bbox_points"]
        box = (
            max(0, int(px0 * sx)),
            max(0, int(py0 * sy)),
            min(image_width, int(px1 * sx + 0.999)),
            min(image_height, int(py1 * sy + 0.999)),
        )
        output.append({
            "number": number,
            "text": region["prompt"],
            "alternatives": region["alternatives"],
            "bbox": [
                box[0] * 1000 / image_width,
                box[1] * 1000 / image_height,
                box[2] * 1000 / image_width,
                box[3] * 1000 / image_height,
            ],
            "confidence": 0.95,
            "needs_review": True,
            "notes": (
                "Questao adicionada pela reconciliacao geometrica da camada textual do PDF "
                "porque a primeira leitura visual nao a detectou. Verificar figuras e contexto."
            ),
            "flags": [
                "Adicionada pelo passe geometrico; revisar figuras/contexto visual manualmente."
            ],
            "geometry_check": {
                "status": "verified",
                "source": "pdfium_text_layer",
                "alternatives_detected": ["A", "B", "C", "D", "E"],
                "bbox_basis": "question_prompt_through_option_E",
            },
        })
        warnings.append(
            f"Page {page_no}: question {number} was recovered from the PDF text layer after first-pass omission."
        )
    return output


def _overlap(a, b):
    return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1])) > 0


def _guard_context_reviews(questions):
    """Legacy local reviews did not receive shared context; keep those records conservative."""
    for q in questions:
        if not q.get("context_images"):
            continue
        audit = q.setdefault("second_review", {
            "provider": "Cloud providers", "status": "uncertain", "issues": [], "notes": "",
        })
        provider = str(audit.get("provider", "")).lower()
        if "ollama" not in provider and "local" not in provider:
            continue
        if audit.get("status") == "complete":
            audit["status"] = "uncertain"
        issues = audit.setdefault("issues", [])
        message = "Esta revisão local antiga não recebeu os contextos compartilhados; conferir manualmente."
        if message not in issues:
            issues.append(message)



def _write_review(folder, questions):
    cards = []
    for q in questions:
        flags = q.get("flags") or ["Sem alertas geometricos automaticos; revisao visual obrigatoria"]
        audit = q.get("second_review") or {}
        status = audit.get("status", "unavailable")
        labels = {
            "complete": "Segundo modelo: aparentemente completo",
            "needs_attention": "Segundo modelo: revisar recorte",
            "uncertain": "Segundo modelo: inconclusivo",
            "unavailable": "Segundo modelo indisponivel",
            "pending_cloud": "Revisao em nuvem pendente — tentar novamente",
            "pending_local": "Pendente na nuvem (estado legado; sera retomado pela nuvem)",
            "not_applicable": "Material complementar: fora da revisao de questao objetiva",
        }
        audit_html = '<p class="audit"><b>' + html.escape(labels.get(status, "Segundo modelo: " + status)) + '</b>'
        issues = audit.get("issues") or []
        if issues:
            audit_html += '<br>' + html.escape("; ".join(str(x) for x in issues))
        if audit.get("notes"):
            audit_html += '<br>' + html.escape(str(audit["notes"]))
        audit_html += '</p>'
        manual = q.get("manual_visual_audit") or {}
        manual_html = ''
        if manual:
            manual_html = '<p class="manual"><b>Conferencia manual: ' + html.escape(str(manual.get("status", "review"))) + '</b><br>' + html.escape(str(manual.get("finding", ""))) + '</p>'
        contexts = q.get("context_images") or []
        context_html = ''.join(
            '<figure class="context"><figcaption>Contexto compartilhado associado</figcaption><img src="' +
            html.escape(str(src)) + '"></figure>' for src in contexts
        )
        cards.append(
            '<article><h2>' + f'P\u00e1gina {q["page"]} \u00b7 Quest\u00e3o ' + html.escape(str(q["number"])) + '</h2>' +
            '<p class="flag">' + html.escape("; ".join(str(x) for x in flags)) + '</p>' +
            audit_html + manual_html +
            '<div class="pair"><figure><figcaption>P\u00e1gina original</figcaption><img src="' +
            html.escape(str(q["page_image"])) + '"></figure><figure><figcaption>Recorte proposto</figcaption><img src="' +
            html.escape(str(q["crop_image"])) + '"></figure></div>' + context_html +
            '<p>' + html.escape(str(q.get("text", ""))[:1600]) + '</p></article>'
        )
    body = "\n".join(cards) or "<p>Nenhuma questao detectada. Confira as paginas.</p>"
    doc = (
        '<!doctype html><html lang="pt-br"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>JARVIS - Revis\u00e3o de prova</title>'
        '<style>body{font:16px system-ui;background:#101722;color:#eef3fa;margin:24px}'
        'h1{color:#79d8ff}article{background:#192536;border:1px solid #34465c;border-radius:12px;padding:18px;margin:20px 0}'
        '.pair{display:grid;grid-template-columns:1fr 1fr;gap:16px}.context{max-width:900px;margin:18px auto;padding:12px;border:1px solid #53657a;border-radius:8px}'
        '.context img{max-height:650px}img{max-width:100%;max-height:850px;object-fit:contain;background:white}'
        'figcaption,.flag{color:#9fc8dc}.audit{color:#ffd38a}.manual{color:#ffadad;border-left:3px solid #d66;padding-left:10px}'
        '@media(max-width:800px){.pair{grid-template-columns:1fr}}</style></head><body>'
        '<h1>Laborat\u00f3rio de Provas - revis\u00e3o obrigat\u00f3ria</h1>'
        '<p>Gemini prop\u00f4s os recortes; a segunda leitura em nuvem confere cada quest\u00e3o e seu contexto. '
        'Os contextos compartilhados aparecem abaixo de cada quest\u00e3o. Compare tudo com a p\u00e1gina original. '
        'Nenhuma quest\u00e3o foi aprovada ou publicada automaticamente.</p>' + body + '</body></html>'
    )
    (folder / "review.html").write_text(doc, encoding="utf-8")


def prepare_exam(path, output_root=None, analyzer=None, second_reviewer=None, review_limit=None):
    path = Path(path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise ValueError("Select a regular PDF or image.")
    if path.stat().st_size <= 0 or path.stat().st_size > MAX_SOURCE_BYTES:
        raise ValueError("Source file must be between 1 byte and 50 MB.")
    path = path.resolve(strict=True)
    if path.suffix.lower() == ".pdf":
        pages = _render_pdf(path)
    elif path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}:
        im = Image.open(path).convert("RGB")
        if max(im.size) > MAX_SIDE:
            im.thumbnail((MAX_SIDE, MAX_SIDE), Image.Resampling.LANCZOS)
        pages = [im]
    else:
        raise ValueError("Supported inputs: PDF, PNG, JPG, WEBP or TIFF.")
    root = Path(output_root) if output_root else Path.home() / "Documents" / "JarvisProjects" / "ExamLab"
    root.mkdir(parents=True, exist_ok=True)
    folder = root / (path.stem + "_" + datetime.now().strftime("%Y%m%d_%H%M%S_%f"))
    folder.mkdir()
    (folder / "pages").mkdir()
    (folder / "crops").mkdir()
    (folder / "contexts").mkdir()
    questions = []
    context_groups = []
    warnings = []
    progress_path = folder / "progress.log"
    def progress(message):
        stamp = datetime.now().isoformat(timespec="seconds")
        with progress_path.open("a", encoding="utf-8") as log:
            log.write(f"[{stamp}] {message}\n")
            log.flush()
    progress(f"START pages={len(pages)} source={path.name}")
    pdf_geometry = {}
    if path.suffix.lower() == ".pdf":
        try:
            pdf_geometry = _pdf_text_question_regions(path)
            total_geometry = sum(len(items) for items in pdf_geometry.values())
            progress(f"PDF_TEXT_GEOMETRY pages={len(pdf_geometry)} complete_questions={total_geometry}")
        except Exception as geometry_exc:
            warnings.append(
                f"PDF text geometry unavailable: {type(geometry_exc).__name__}: {geometry_exc}"
            )
            progress(f"PDF_TEXT_GEOMETRY_FAILED {type(geometry_exc).__name__}: {geometry_exc}")
    for page_no, page in enumerate(pages, 1):
        progress(f"PAGE {page_no}/{len(pages)} first-pass_start")
        page_rel = f"pages/page_{page_no:03}.jpg"
        page.save(folder / page_rel, quality=92)
        try:
            data, analyzed = (analyzer or _analyze_page)(page, page_no)
        except Exception as exc:
            warnings.append(
                f"Page {page_no}: cloud analysis unavailable; page skipped without local AI: "
                f"{type(exc).__name__}: {exc}"
            )
            progress(f"PAGE {page_no} cloud-analysis_unavailable; kept for a later cloud retry")
            continue
        progress(f"PAGE {page_no} first-pass_ok questions={len(data.get('questions', []) or [])} contexts={len(data.get('shared_contexts', []) or [])}")
        # Save shared reading passages and visual references as separate assets.
        for cidx, ctx in enumerate(data.get("shared_contexts", []) or [], 1):
            ctx_id = str(ctx.get("id", "")).casefold() if isinstance(ctx, dict) else ""
            ctx_kind = str(ctx.get("kind", "")).casefold() if isinstance(ctx, dict) else ""
            ctx_notes = str(ctx.get("notes", "")).casefold() if isinstance(ctx, dict) else ""
            if (
                "cover" in ctx_id or "cover" in ctx_kind
                or ctx_kind in ("cover_page", "candidate_identification")
                or ("capa" in ctx_notes and page_no == 1)
                or ("nome do candidato" in ctx_notes and page_no == 1)
            ):
                warnings.append(
                    f"Page {page_no}: candidate/cover material was excluded from objective-question contexts."
                )
                continue
            if not isinstance(ctx, dict):
                continue
            try:
                context_box = _box_pixels(ctx.get("bbox"), analyzed.width, analyzed.height)
                pad_x = max(2, int(analyzed.width * 0.04))
                pad_y = max(2, int(analyzed.height * 0.04))
                context_box = (
                    max(0, context_box[0] - pad_x), max(0, context_box[1] - pad_y),
                    min(analyzed.width, context_box[2] + pad_x),
                    min(analyzed.height, context_box[3] + pad_y),
                )
            except Exception as exc:
                warnings.append(f"Page {page_no}, context {cidx}: invalid box: {exc}")
                continue
            raw_id = str(ctx.get("id") or f"context_{cidx}")
            safe_id = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_id).strip("_")[:48] or f"context_{cidx}"
            context_rel = f"contexts/page_{page_no:03}_{safe_id}.png"
            analyzed.crop(context_box).save(folder / context_rel)
            applies = ctx.get("applies_to_numbers", [])
            if not isinstance(applies, list):
                applies = []
            applies = [str(x).strip().zfill(2) if str(x).strip().isdigit() else str(x).strip() for x in applies]
            applies_range = ctx.get("applies_to_range")
            if isinstance(applies_range, (list, tuple)) and len(applies_range) == 2:
                try:
                    first_number, last_number = int(applies_range[0]), int(applies_range[1])
                    if 1 <= first_number <= last_number <= 200:
                        applies.extend(f"{n:02d}" for n in range(first_number, last_number + 1))
                except (TypeError, ValueError):
                    warnings.append(f"Page {page_no}, context {safe_id}: invalid question range.")
            applies = list(dict.fromkeys(applies))
            context_groups.append({
                "id": safe_id, "kind": str(ctx.get("kind", "shared_context")),
                "source_page": page_no, "image": context_rel,
                "applies_to_numbers": applies,
                "confidence": float(ctx.get("confidence", 0) or 0),
                "notes": str(ctx.get("notes", "")),
                "review_status": "pending_human_review",
            })
        prior = []
        page_questions = []
        raw_questions = data.get("questions", []) or []
        page_geometry = pdf_geometry.get(page_no, [])
        if page_geometry:
            raw_questions = _reconcile_page_questions(
                raw_questions, page_geometry, analyzed.width, analyzed.height, warnings, page_no
            )
        elif path.suffix.lower() == ".pdf":
            for raw_question in raw_questions:
                if isinstance(raw_question, dict):
                    raw_question.setdefault("flags", []).append(
                        "Sem verificacao independente das alternativas pela camada textual do PDF."
                    )
        missing_boxes = []
        for raw_idx, raw_q in enumerate(raw_questions, 1):
            try:
                _box_pixels(raw_q.get("bbox"), analyzed.width, analyzed.height)
            except Exception:
                missing_boxes.append((raw_idx, raw_q))
        if missing_boxes:
            progress(f"PAGE {page_no} bbox_repair_start missing={len(missing_boxes)}")
            try:
                repaired = _repair_missing_boxes(analyzed, page_no, missing_boxes)
                for raw_idx, raw_q in missing_boxes:
                    if raw_idx in repaired:
                        raw_q["bbox"] = repaired[raw_idx]
                progress(f"PAGE {page_no} bbox_repair_done repaired={len(repaired)}/{len(missing_boxes)}")
            except Exception as repair_exc:
                warnings.append(f"Page {page_no}: bbox repair failed: {type(repair_exc).__name__}: {repair_exc}")
                progress(f"PAGE {page_no} bbox_repair_failed {type(repair_exc).__name__}: {repair_exc}")
        valid_boxes = {}
        for raw_idx, raw_q in enumerate(raw_questions, 1):
            try:
                valid_boxes[raw_idx] = _box_pixels(raw_q.get("bbox"), analyzed.width, analyzed.height)
            except Exception:
                pass
        tightened_boxes = _tighten_overlapping_boxes(valid_boxes, analyzed.width, analyzed.height)
        for idx, q in enumerate(raw_questions, 1):
            flags = []
            try:
                box = tightened_boxes.get(idx) or _box_pixels(q.get("bbox"), analyzed.width, analyzed.height)
            except Exception as exc:
                warnings.append(f"Page {page_no}, item {idx}: invalid box: {exc}")
                continue
            x0, y0, x1, y1 = box
            if x1 - x0 < 80 or y1 - y0 < 45:
                flags.append("Recorte muito pequeno")
            gray = analyzed.crop(box).convert("L")
            if gray.getextrema()[0] == gray.getextrema()[1]:
                flags.append("Recorte parece uniforme ou em branco")
            else:
                sample = list(gray.resize((min(120, gray.width), min(120, gray.height))).getdata())
                if statistics.pstdev(sample) < 8:
                    flags.append("Baixo contraste aparente")
            if x0 < 3 or y0 < 3 or analyzed.width - x1 < 3 or analyzed.height - y1 < 3:
                flags.append("Recorte encosta na borda da pÃ¡gina")
            confidence = float(q.get("confidence", 0) or 0)
            if confidence < 0.85:
                flags.append("Baixa confianÃ§a")
            if q.get("needs_review"):
                flags.append("IA solicitou revisÃ£o")
            if q.get("continues_next_page"):
                flags.append("QuestÃ£o continua na prÃ³xima pÃ¡gina")
            if any(_overlap(box, b) for b in prior):
                flags.append("SobreposiÃ§Ã£o com outra questÃ£o")
            prior.append(box)
            crop_rel = f"crops/page_{page_no:03}_question_{idx:03}.png"
            analyzed.crop(box).save(folder / crop_rel)
            item = {
                "page": page_no, "number": str(q.get("number", idx)),
                "text": str(q.get("text", "")),
                "alternatives": q.get("alternatives", []) if isinstance(q.get("alternatives", []), list) else [],
                "confidence": confidence, "bbox": list(box),
                "page_image": page_rel, "crop_image": crop_rel,
                "flags": sorted(set(flags)), "review_status": "pending_review",
                "notes": str(q.get("notes", "")),
            }
            questions.append(item)
            page_questions.append(item)
        partial = {
            "source": path.name, "pages_total": len(pages), "pages_processed": page_no,
            "questions_extracted": len(questions), "context_groups": context_groups,
            "questions": questions, "warnings": warnings,
        }
        (folder / "extraction_progress.json").write_text(
            json.dumps(partial, ensure_ascii=False, indent=2), encoding="utf-8")
        progress(f"PAGE {page_no}/{len(pages)} extraction_checkpoint questions_total={len(questions)}")
    progress(f"EXTRACTION_COMPLETE questions={len(questions)} contexts={len(context_groups)}; linking_contexts")
    # Attach shared assets after all pages are processed, so a passage on one
    # page can be linked to questions printed on the following page.
    known_numbers = {str(q.get("number", "")).strip().zfill(2) for q in questions}
    for group in context_groups:
        matched = 0
        for q in questions:
            number = str(q.get("number", "")).strip()
            number = number.zfill(2) if number.isdigit() else number
            if number in group["applies_to_numbers"]:
                q.setdefault("context_images", []).append(group["image"])
                q.setdefault("context_notes", []).append(group["notes"] or group["kind"])
                matched += 1
        if not matched:
            warnings.append(f"Shared context {group['id']} was not linked to any detected question number.")
    questions.sort(
        key=lambda item: (
            int(item.get("number")) if str(item.get("number", "")).isdigit() else 9999,
            int(item.get("page", 0) or 0),
        )
    )
    # Defensive cleanup: never associate a cover/candidate header with a question.
    cover_images = {
        group.get("image") for group in context_groups
        if "cover" in str(group.get("id", "")).casefold()
        or "cover" in str(group.get("kind", "")).casefold()
        or str(group.get("kind", "")).casefold() in ("cover_page", "candidate_identification")
    }
    if cover_images:
        context_groups = [group for group in context_groups if group.get("image") not in cover_images]
        for question in questions:
            question["context_images"] = [
                image for image in (question.get("context_images") or [])
                if image not in cover_images
            ]
            question["context_notes"] = [
                note for note in (question.get("context_notes") or [])
                if "capa" not in str(note).casefold() and "cover" not in str(note).casefold()
            ]

    # Persist the complete extraction before cloud review. If a quota or network
    # error interrupts the second pass, the report and crops remain recoverable.
    manifest = {
        "source": path.name, "created_at": datetime.now().isoformat(timespec="seconds"),
        "review_required": True, "pipeline": {
            "first_model": EXAM_CLOUD_MODEL + " vision",
            "second_model": EXAM_CLOUD_MODEL + " cloud per-question; configured remote vision provider / Gemini cloud ladder fallback",
            "cloud_model_pinned": EXAM_CLOUD_MODEL, "cloud_fallback_to_other_models": True,
            "openai_api_used": False,
        },
        "questions": questions, "context_groups": context_groups, "warnings": warnings,
    }
    for item in questions:
        item["second_review"] = {
            "provider": "Gemini cloud", "status": "pending_cloud",
            "issues": ["A segunda leitura em nuvem ainda nao foi executada."], "notes": "",
        }

    def save_checkpoint():
        manifest["questions"] = questions
        manifest["context_groups"] = context_groups
        manifest["warnings"] = warnings
        _write_review(folder, questions)
        (folder / "questions.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    save_checkpoint()
    progress(f"CLOUD_REVIEW_START questions={len(questions)}")
    # Shared reading material is linked before any second-pass review.
    reviewed_now = 0
    for page_no in sorted({q["page"] for q in questions}):
        if review_limit and reviewed_now >= review_limit:
            progress(f"CLOUD_REVIEW_BATCH_PAUSED reviewed={reviewed_now}")
            break
        page_questions = [q for q in questions if q["page"] == page_no]
        progress(f"CLOUD_PAGE {page_no} start questions={len(page_questions)}")
        try:
            reviews = second_reviewer(None, page_no, page_questions) if second_reviewer else _cloud_second_review(folder, page_no, page_questions)
            if reviews is None:
                raise RuntimeError("A revisao em nuvem nao retornou resposta utilizavel.")
            for idx, item in enumerate(page_questions, 1):
                item["second_review"] = reviews.get(idx, {
                    "provider": "Gemini cloud", "status": "uncertain",
                    "issues": ["A revisao nao retornou resultado para esta questao."], "notes": ""})
        except Exception as cloud_exc:
            if second_reviewer is not None:
                for item in page_questions:
                    item["second_review"] = {
                        "provider": "Injected reviewer", "status": "unavailable",
                        "issues": ["O revisor de teste/customizado falhou."],
                        "notes": str(cloud_exc)[:300],
                    }
                warnings.append(
                    f"Page {page_no}: injected reviewer unavailable: {type(cloud_exc).__name__}: {cloud_exc}"
                )
            else:
                warnings.append(
                    f"Page {page_no}: cloud review unavailable; queued for a later cloud retry: "
                    f"{type(cloud_exc).__name__}: {cloud_exc}"
                )
                for item in page_questions:
                    item["second_review"] = {
                        "provider": "Gemini + configured cloud vision provider",
                        "status": "pending_cloud",
                        "issues": ["A revisão em nuvem não pôde ser concluída; tente novamente mais tarde. Nenhum modelo local foi iniciado."],
                        "notes": str(cloud_exc)[:300],
                    }
        _guard_context_reviews(page_questions)
        save_checkpoint()
        progress(f"CLOUD_PAGE {page_no} checkpoint_saved")
        reviewed_now += len(page_questions)
    for q in questions:
        if re.search(r"\b(tirinha|quadrinho|charge|figura|imagem|grafico|tabela|mapa|ilustracao)\b", q.get("text", ""), re.I) and not q.get("context_images"):
            q.setdefault("flags", []).append("Questao faz referencia a elemento visual; conferir contexto associado.")
    save_checkpoint()
    progress("COMPLETE report_saved")
    return folder, manifest


def resume_cloud_review(folder, review_limit=None, strict_pending=False):
    """Resume pending cloud audits from an existing questions.json checkpoint."""
    folder = Path(folder).resolve(strict=True)
    manifest_path = folder / "questions.json"
    if not manifest_path.is_file():
        raise ValueError("No questions.json checkpoint exists in this exam folder.")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    questions = manifest.get("questions", [])
    if not isinstance(questions, list):
        raise ValueError("The checkpoint has no valid questions list.")
    progress_path = folder / "progress.log"

    def progress(message):
        stamp = datetime.now().isoformat(timespec="seconds")
        with progress_path.open("a", encoding="utf-8") as log:
            log.write(f"[{stamp}] {message}\n")
            log.flush()

    def save():
        manifest["questions"] = questions
        _write_review(folder, questions)
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def is_pending(q):
        st = q.get("second_review", {}).get("status")
        return st in ("pending_cloud", "pending_local") if strict_pending else st != "complete"

    reviewed_now = 0
    pending_pages = sorted({
        q.get("page") for q in questions
        if is_pending(q)
    })
    progress(f"RESUME_CLOUD_REVIEW_START pending_pages={len(pending_pages)} pending_questions={sum(is_pending(q) for q in questions)}")
    for page_no in pending_pages:
        if review_limit and reviewed_now >= review_limit:
            progress(f"CLOUD_REVIEW_BATCH_PAUSED reviewed={reviewed_now}")
            break
        page_questions = [
            q for q in questions
            if q.get("page") == page_no and is_pending(q)
        ]
        progress(f"RESUME_CLOUD_PAGE {page_no} start questions={len(page_questions)}")
        try:
            reviews = _cloud_second_review(folder, page_no, page_questions)
            if reviews is None:
                raise RuntimeError("Cloud review returned no usable response.")
            for idx, item in enumerate(page_questions, 1):
                item["second_review"] = reviews.get(idx, {
                    "provider": "Gemini cloud", "status": "uncertain",
                    "issues": ["No second-review result returned for this question."], "notes": ""})
        except Exception as exc:
            manifest.setdefault("warnings", []).append(
                f"Resume cloud review page {page_no} failed; kept pending for cloud retry: "
                f"{type(exc).__name__}: {exc}"
            )
            for item in page_questions:
                item["second_review"] = {
                    "provider": "Gemini + configured cloud vision provider (retry later)",
                    "status": "pending_cloud",
                    "issues": ["A revisão em nuvem falhou; a questão continuará pendente para nova tentativa."],
                    "notes": str(exc)[:300],
                }
        _guard_context_reviews(page_questions)
        save()
        progress(f"RESUME_CLOUD_PAGE {page_no} checkpoint_saved")
        reviewed_now += len(page_questions)
    progress("RESUME_CLOUD_REVIEW_COMPLETE")
    return folder, manifest


PLUGIN = {
    "name": "exam_lab",
    "description": "Prepare a selected exam PDF or image. Uses pinned Gemini 3.1 Flash-Lite first, then configured remote vision providers and the Gemini cloud ladder when quota is exhausted. No local AI model is required. Creates side-by-side review and questions.json; every crop remains pending human approval.",
    "tier": "core", "behavior": "NON_BLOCKING",
    "parameters": {"type": "OBJECT", "properties": {"action": {"type": "STRING", "enum": ["prepare"]}}, "required": ["action"]},
}


def run(parameters, player=None, session_memory=None):
    selected = getattr(player, "current_file", None) if player is not None else None
    if callable(selected):
        selected = selected()
    if not selected:
        return "Selecione ou arraste uma prova PDF/imagem para a caixa de arquivos do JARVIS primeiro."
    try:
        path = Path(str(selected)).expanduser()
        folder, manifest = prepare_exam(path)
        flagged = sum(bool(q["flags"]) for q in manifest["questions"])
        needs_attention = sum(q.get("second_review", {}).get("status") == "needs_attention" for q in manifest["questions"])
        uncertain = sum(q.get("second_review", {}).get("status") in {"uncertain", "unavailable"} for q in manifest["questions"])
        pending_cloud = sum(q.get("second_review", {}).get("status") in {"pending_cloud", "pending_local"} for q in manifest["questions"])
        pages = len({q["page"] for q in manifest["questions"]})
        return (
            f"LaboratÃ³rio gerou {len(manifest['questions'])} recortes em {pages} pÃ¡ginas; "
            f"{flagged} tÃªm alertas geomÃ©tricos, {needs_attention} foram sinalizados pelo segundo modelo, "
            f"{uncertain} ficaram inconclusivos e {pending_cloud} aguardam nova tentativa na nuvem. "
            f"Nenhum modelo local foi iniciado. "
            f"Todos seguem pendentes de aprovaÃ§Ã£o. Abra {folder/'review.html'} e confira cada recorte. "
            f"JSON: {folder/'questions.json'}. Nada foi publicado no Lerum."
        )
    except Exception as exc:
        return f"NÃ£o consegui preparar a prova: {exc}"



