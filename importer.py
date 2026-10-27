"""解析 xingcezhenti 仓库的 markdown 真题并导入 SQLite
改动：clean_html 存 <img> 路径、split_materials 扩到所有模块、
     每道题存 shared_passage 和 images（绝对路径）
"""
import json
import os
import re
import sys

from db import get_conn

FRONT_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
KV_RE = re.compile(r'^(\S+?):\s*"(.*?)"\s*$', re.M)

QHEAD_A = re.compile(r"^## 第\s*(\d+)\s*题\s*<sub>qid\s*(\d+)\s*·\s*(.*?)</sub>\s*$", re.M)
QHEAD_B = re.compile(r"^### 第\s*(\d+)\s*题\s*<sub>qid\s*(\d+)\s*·\s*(.*?)</sub>\s*$", re.M)

OPT_RE = re.compile(r"^-\s*\*\*([A-Z])\*\*\.\s*(.*?)\s*$", re.M)
ANS_RE = re.compile(r"\*\*答案\*\*：\s*([A-Z]+)")
ANAL_RE = re.compile(r"\*\*官方解析\*\*\s*\n")

RA_OPT_RE = re.compile(r"([A-D])项[：:](.*?)(?=[A-D]项[：:]|$)", re.S)
HTML_TAG_RE = re.compile(r"<[^>]+>")
OPT_LINE_RE = re.compile(r"^\s*-\s*\*\*[A-D]\*\*[\.．]\s*.*$", re.M)
MATERIAL_RE = re.compile(r"^##\s*材料\s*(\S+)\s*$", re.M)

# 提取 <img src="..."> 的 src，用于存绝对路径
IMG_SRC_RE = re.compile(r'<img[^>]*src="([^"]+)"[^>]*/>', re.I)


def clean_html(text, base_dir=None):
    """清 HTML，返回 (纯文本, 图片绝对路径列表)
    base_dir: md 文件所在目录，用于把 <img src="..."> 转绝对路径
    """
    images = []
    if not text:
        return "", images
    # 先提所有 <img> 的 src，转绝对路径收集
    for m in IMG_SRC_RE.finditer(text):
        src = m.group(1).strip()
        if src and base_dir:
            abs_path = os.path.abspath(os.path.join(base_dir, src))
            if os.path.isfile(abs_path) and abs_path not in images:
                images.append(abs_path)
        # 不管能不能转绝对路径，都把 <img> 从文本里剥掉
        text = text[:m.start()] + "[图]" + text[m.end():]
    # 处理裸 <img />（有 img 但无 src 或 src 非法）
    text = re.sub(r'<img[^>]*/>', "[图]", text, flags=re.I)
    # 清其他 HTML 标签
    text = HTML_TAG_RE.sub("", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = OPT_LINE_RE.sub("", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip(), images


def parse_frontmatter(text):
    m = FRONT_RE.match(text)
    meta = {}
    if m:
        meta = dict(KV_RE.findall(m.group(1)))
        text = text[m.end():]
    return meta, text


def split_materials(body):
    """返回 [(材料号, 起始offset, 结束offset, 材料正文)] 列表
    所有模块只要 md 里有 ## 材料 N 标记都会提取
    """
    mats = []
    matches = list(MATERIAL_RE.finditer(body))
    if not matches:
        return mats
    for i, m in enumerate(matches):
        num = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        next_q = re.search(r"^(?:##|###)\s*第\s*\d+\s*题", body[start:end], re.M)
        text_end = start + next_q.start() if next_q else end
        # 材料正文只做基础 clean（不去 img，保留 <img> 让调用方统一处理）
        mats.append((num, m.start(), end, body[start:text_end].strip()))
    return mats


def find_material_for_offset(mats, offset):
    """给定 body 中的 offset，找它属于哪个材料 [m_start, m_end)"""
    for num, m_start, m_end, raw_text in mats:
        if offset < m_start:
            break
        if offset < m_end:
            return num, raw_text
    return None, ""


def extract_ra_options(analysis):
    opts = {"A": "", "B": "", "C": "", "D": ""}
    found = RA_OPT_RE.findall(analysis)
    for letter, text in found:
        t, _ = clean_html(text)
        opts[letter] = t[:300]
    return opts


def parse_paper(path):
    base_dir = os.path.dirname(path)
    with open(path, encoding="utf-8") as f:
        text = f.read()
    meta, body = parse_frontmatter(text)

    heads = list(QHEAD_A.finditer(body))
    if not heads:
        heads = list(QHEAD_B.finditer(body))
    if not heads:
        return meta, []

    module = meta.get("模块", "")
    is_ra = "资料分析" in module
    # 所有模块都尝试提取共享材料（之前只给资料分析做）
    mats = split_materials(body)

    questions = []
    for i, h in enumerate(heads):
        seq, qid, subtype = int(h.group(1)), h.group(2), h.group(3).strip()
        seg_start = h.end()
        seg_end = heads[i + 1].start() if i + 1 < len(heads) else len(body)
        seg = body[seg_start:seg_end]

        ans_m = ANS_RE.search(seg)
        answer = ans_m.group(1) if ans_m else ""
        if not answer:
            continue

        mat_num, mat_raw = find_material_for_offset(mats, h.start())

        if is_ra and ans_m:
            ans_before = seg[: ans_m.start()].strip()
            ans_before = re.sub(r"^##\s*材料\s*\S+\s*\n", "", ans_before, count=1).strip()
            stem, imgs = clean_html(ans_before, base_dir)
            analysis_body = seg[ans_m.end():].strip()
            analysis_clean, a_imgs = clean_html(analysis_body, base_dir)
            imgs.extend(a_imgs)
            opts = extract_ra_options(analysis_body)
            shared_passage = None
            if mat_raw:
                mat_text, m_imgs = clean_html(mat_raw, base_dir)
                imgs = m_imgs + imgs
                # 资料分析：材料拼进 stem 前面（历史行为，保持兼容）
                stem = f"【材料{mat_num}】\n{mat_text}\n\n{stem}" if stem else f"【材料{mat_num}】\n{mat_text}"
        else:
            stem_part = seg[: ans_m.start()].strip() if ans_m else seg.strip()
            options = dict(OPT_RE.findall(stem_part))
            first_opt = re.search(r"^-\s*\*\*A\*\*\.", stem_part, re.M)
            raw_stem = stem_part[: first_opt.start()].strip() if first_opt else stem_part.strip()
            stem, imgs = clean_html(raw_stem, base_dir)
            shared_passage = None
            # 非资料分析模块也存 shared_passage 字段（GUI 单独显示，不拼进 stem）
            if mat_raw:
                mat_text, m_imgs = clean_html(mat_raw, base_dir)
                imgs = m_imgs + imgs
                shared_passage = f"【材料{mat_num}】{mat_text}" if mat_text else None
            an_m = ANAL_RE.search(seg)
            raw_analysis = seg[an_m.end():].strip() if an_m else ""
            raw_analysis = re.sub(r"\n?-{3,}\s*$", "", raw_analysis).strip()
            analysis_clean, a_imgs = clean_html(raw_analysis, base_dir)
            imgs.extend(a_imgs)
            opts = {k: clean_html(v.replace("✅", "").strip(), base_dir)[0] for k, v in options.items()}

        if not stem or not answer:
            continue
        # 去重复图片路径
        seen = set(); imgs = [p for p in imgs if not (p in seen or seen.add(p))]

        questions.append({
            "qid": qid, "seq": seq, "subtype": subtype,
            "stem": stem, "answer": answer,
            "analysis": analysis_clean,
            "option_a": opts.get("A", ""),
            "option_b": opts.get("B", ""),
            "option_c": opts.get("C", ""),
            "option_d": opts.get("D", ""),
            "shared_passage": shared_passage,
            "images": json.dumps(imgs, ensure_ascii=False) if imgs else None,
        })
    return meta, questions


def import_dir(root):
    conn = get_conn()
    # 首次全量导入前清库（避免老库字段不全）
    existing = conn.execute("PRAGMA table_info(questions)").fetchall()
    has_data = conn.execute("SELECT COUNT(*) c FROM questions").fetchone()["c"]
    cols_have = {r[1] for r in existing}
    if has_data and ("shared_passage" not in cols_have or "images" not in cols_have):
        print("[importer] 检测到旧库缺新字段，清库重导...")
        conn.execute("DELETE FROM questions")
        conn.execute("DELETE FROM progress")
        conn.commit()

    inserted = skipped = 0
    for dirpath, _, files in os.walk(root):
        for fn in sorted(files):
            if not fn.endswith(".md"):
                continue
            path = os.path.join(dirpath, fn)
            try:
                meta, qs = parse_paper(path)
            except Exception as e:
                print(f"[解析失败] {path}: {e}")
                continue
            for q in qs:
                try:
                    conn.execute(
                        """INSERT OR IGNORE INTO questions
                           (qid, paper, region, year, module, subtype, seq,
                            stem, option_a, option_b, option_c, option_d,
                            answer, analysis, source_file, shared_passage, images)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (q["qid"], meta.get("试卷", fn[:-3]), meta.get("地区", ""),
                         meta.get("年份", ""), meta.get("模块", os.path.basename(dirpath)),
                         q["subtype"], q["seq"], q["stem"],
                         q["option_a"], q["option_b"], q["option_c"], q["option_d"],
                         q["answer"], q["analysis"], os.path.relpath(path, root),
                         q["shared_passage"], q["images"]),
                    )
                    if conn.total_changes > 0:
                        inserted += 1
                    else:
                        skipped += 1
                except Exception as e:
                    skipped += 1
                    print(f"[入库失败] {fn} 第{q['seq']}题: {e}")
        conn.commit()
    total = conn.execute("SELECT COUNT(*) c FROM questions").fetchone()["c"]
    with_img = conn.execute("SELECT COUNT(*) c FROM questions WHERE images IS NOT NULL AND images != '[]'").fetchone()["c"]
    with_pass = conn.execute("SELECT COUNT(*) c FROM questions WHERE shared_passage IS NOT NULL").fetchone()["c"]
    conn.close()
    print(f"导入完成：新增 {inserted}，跳过 {skipped}，总计 {total} 题")
    print(f"  含图题：{with_img}，含共享材料题：{with_pass}")


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "repo")
    import_dir(root)
