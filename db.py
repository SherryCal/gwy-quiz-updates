"""SQLite 题库与刷题进度数据库"""
import json
import os
import shutil
import sqlite3
import sys


def _app_support_dir():
    """返回用户可写的应用数据目录（首次自动建）"""
    if sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    elif sys.platform.startswith("win"):
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    else:
        base = os.path.expanduser("~")
    d = os.path.join(base, "gwy-quiz")
    os.makedirs(d, exist_ok=True)
    return d


def _find_db():
    """定位数据库：优先用户目录可写的，没有就从打包资源或开发目录复制过去"""
    env_home = os.environ.get("GWY_QUIZ_HOME")
    if env_home:
        os.makedirs(env_home, exist_ok=True)
        return os.path.join(env_home, "gwy_quiz.db")

    dest_dir = _app_support_dir()
    dest = os.path.join(dest_dir, "gwy_quiz.db")
    if os.path.exists(dest):
        return dest  # 已经有了

    # 首次运行：找打包资源或开发目录里的 gwy_quiz.db 复制过去
    if getattr(sys, "frozen", False):
        candidates = [
            os.path.join(sys._MEIPASS, "data", "gwy_quiz.db"),
            os.path.join(sys._MEIPASS, "gwy_quiz.db"),
        ]
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        candidates = [os.path.join(here, "data", "gwy_quiz.db")]

    for src in candidates:
        if os.path.isfile(src) and os.path.getsize(src) > 1024:
            shutil.copy2(src, dest)
            print(f"[gwy-quiz] 题库已复制到 {dest}")
            return dest

    # 真的找不到——直接在可写目录建空库
    print(f"[gwy-quiz] 题库文件不存在，首次运行将建空库于 {dest}")
    return dest


DB_PATH = _find_db()

SCHEMA = """
CREATE TABLE IF NOT EXISTS questions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    qid             TEXT,
    paper           TEXT NOT NULL,
    region          TEXT,
    year            TEXT,
    module          TEXT NOT NULL,
    subtype         TEXT,
    seq             INTEGER,
    stem            TEXT NOT NULL,
    option_a        TEXT,
    option_b        TEXT,
    option_c        TEXT,
    option_d        TEXT,
    answer          TEXT NOT NULL,
    analysis        TEXT,
    source_file     TEXT,
    shared_passage  TEXT,                -- 共享文章/材料（一材多题的"材"）
    images          TEXT,                -- JSON 数组，每元素是图片绝对路径（GUI渲图用）
    UNIQUE(qid, paper, module)
);
CREATE INDEX IF NOT EXISTS idx_q_module ON questions(module);
CREATE INDEX IF NOT EXISTS idx_q_year   ON questions(year);
CREATE INDEX IF NOT EXISTS idx_q_paper  ON questions(paper);

CREATE TABLE IF NOT EXISTS progress (
    question_id INTEGER PRIMARY KEY REFERENCES questions(id),
    attempts    INTEGER NOT NULL DEFAULT 0,
    wrong       INTEGER NOT NULL DEFAULT 0,
    last_chosen TEXT,
    last_at     TEXT
);
"""


def get_conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    _migrate(conn)  # 给旧库补新列
    return conn


def _migrate(conn):
    """给早期版本的库补 shared_passage / images 列"""
    cols = [r[1] for r in conn.execute("PRAGMA table_info(questions)").fetchall()]
    if "shared_passage" not in cols:
        conn.execute("ALTER TABLE questions ADD COLUMN shared_passage TEXT")
    if "images" not in cols:
        conn.execute("ALTER TABLE questions ADD COLUMN images TEXT")


def record_answer(conn, question_id, chosen, correct):
    conn.execute(
        """INSERT INTO progress(question_id, attempts, wrong, last_chosen, last_at)
           VALUES(?, 1, ?, ?, datetime('now', 'localtime'))
           ON CONFLICT(question_id) DO UPDATE SET
               attempts = attempts + 1,
               wrong = wrong + ?,
               last_chosen = excluded.last_chosen,
               last_at = excluded.last_at""",
        (question_id, 0 if correct else 1, chosen, 0 if correct else 1),
    )
    conn.commit()


def fetch_questions(conn, module=None, year=None, paper=None, region=None,
                    wrong_only=False, unanswered_only=False, limit=None,
                    random_order=False):
    sql = "SELECT q.* FROM questions q"
    where, params = [], []
    if wrong_only or unanswered_only:
        sql += " LEFT JOIN progress p ON p.question_id = q.id"
    if module:
        where.append("q.module = ?"); params.append(module)
    if year:
        where.append("q.year = ?"); params.append(year)
    if paper:
        where.append("q.paper = ?"); params.append(paper)
    if region:
        where.append("q.region = ?"); params.append(region)
    if wrong_only:
        where.append("p.wrong > 0")
    if unanswered_only:
        where.append("p.question_id IS NULL")
    if where:
        sql += " WHERE " + " AND ".join(where)
    if random_order:
        sql += " ORDER BY RANDOM()"
    elif paper:
        # 套卷模式：同一张卷内，先按模块（常识→言语→数量→判断→资料）
        # 再按 seq 排，这样题号不会跨模块跳跃
        module_order = ("政治理论", "常识判断", "言语理解与表达",
                        "数量关系", "判断推理", "资料分析")
        case_parts = [f"WHEN '{m}' THEN {i}" for i, m in enumerate(module_order)]
        sql += (f" ORDER BY CASE q.module " + " ".join(case_parts) +
                f" ELSE 99 END, q.seq")
    else:
        sql += " ORDER BY q.year DESC, q.paper, q.seq"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return conn.execute(sql, params).fetchall()


def list_filter_values(conn, column):
    assert column in ("module", "year", "paper", "region")
    rows = conn.execute(
        f"SELECT DISTINCT {column} v FROM questions WHERE {column} IS NOT NULL AND {column} != '' ORDER BY v DESC"
    ).fetchall()
    return [r["v"] for r in rows]


def stats(conn):
    total = conn.execute("SELECT COUNT(*) c FROM questions").fetchone()["c"]
    done = conn.execute("SELECT COUNT(*) c FROM progress WHERE attempts > 0").fetchone()["c"]
    wrong = conn.execute("SELECT COUNT(*) c FROM progress WHERE wrong > 0").fetchone()["c"]
    att = conn.execute("SELECT COALESCE(SUM(attempts),0) a, COALESCE(SUM(wrong),0) w FROM progress").fetchone()
    rate = (1 - att["w"] / att["a"]) * 100 if att["a"] else 0.0
    return {"total": total, "done": done, "wrong": wrong, "rate": rate}


# ---------- 时间维度统计（日报/周报/月报） ----------

def _bucket(period):
    """SQLite strftime 格式：day=%Y-%m-%d  week=周一起始  month=%Y-%m"""
    return {"day": "%Y-%m-%d", "week": "%Y-W%W", "month": "%Y-%m"}[period]


def _period_where(period, conn):
    """返回 (where_clause, params) 限定该 period 的时间范围
    注意：last_at 存的就是本地时间(datetime('now','localtime'))，
    查询时不能再加 'localtime' 修饰符，否则会被二次 +8 小时"""
    if period == "day":
        return "AND date(p.last_at) = date('now', 'localtime')", []
    if period == "week":
        return (
            "AND strftime('%Y-W%W', p.last_at) = strftime('%Y-W%W', date('now','localtime'))",
            [],
        )
    if period == "month":
        return (
            "AND strftime('%Y-%m', p.last_at) = strftime('%Y-%m', date('now','localtime'))",
            [],
        )
    return "", []


def stats_overall(conn, period="day"):
    """返回该 period 的总量统计 dict"""
    where, params = _period_where(period, conn)
    row = conn.execute(
        f"""SELECT COALESCE(SUM(p.attempts),0) attempts,
                   COALESCE(SUM(p.wrong),0) wrong,
                   COUNT(DISTINCT p.question_id) unique_q
            FROM progress p
            WHERE p.last_at IS NOT NULL {where}""",
        params,
    ).fetchone()
    a = row["attempts"] or 0
    w = row["wrong"] or 0
    return {
        "attempts": a,
        "wrong": w,
        "correct": a - w,
        "unique_q": row["unique_q"] or 0,
        "rate": round((1 - w / a) * 100, 1) if a else 0.0,
    }


def stats_by_module(conn, period="day"):
    """返回 [(module, attempts, wrong, unique_q, rate), ...] 按 attempts 降序"""
    where, params = _period_where(period, conn)
    rows = conn.execute(
        f"""SELECT q.module,
                   COALESCE(SUM(p.attempts),0) attempts,
                   COALESCE(SUM(p.wrong),0) wrong,
                   COUNT(DISTINCT p.question_id) unique_q
            FROM progress p
            JOIN questions q ON q.id = p.question_id
            WHERE p.last_at IS NOT NULL {where}
            GROUP BY q.module
            ORDER BY attempts DESC""",
        params,
    ).fetchall()
    out = []
    for r in rows:
        a = r["attempts"] or 0
        w = r["wrong"] or 0
        out.append({
            "module": r["module"],
            "attempts": a,
            "wrong": w,
            "correct": a - w,
            "unique_q": r["unique_q"] or 0,
            "rate": round((1 - w / a) * 100, 1) if a else 0.0,
        })
    return out


def stats_trend(conn, period="day", limit=7):
    """返回最近 N 个时间桶的总量，用于画趋势
    day: 最近 7 天, week: 最近 8 周, month: 最近 6 月"""
    fmt = _bucket(period)
    rows = conn.execute(
        f"""SELECT strftime('{fmt}', p.last_at) bucket,
                   COALESCE(SUM(p.attempts),0) attempts,
                   COALESCE(SUM(p.wrong),0) wrong,
                   COUNT(DISTINCT p.question_id) unique_q
            FROM progress p
            WHERE p.last_at IS NOT NULL
            GROUP BY bucket
            ORDER BY bucket DESC
            LIMIT {int(limit)}"""
    ).fetchall()
    rows = list(reversed(rows))  # 升序
    out = []
    for r in rows:
        a = r["attempts"] or 0
        w = r["wrong"] or 0
        out.append({
            "bucket": r["bucket"],
            "attempts": a,
            "wrong": w,
            "rate": round((1 - w / a) * 100, 1) if a else 0.0,
        })
    return out


def _count_streak(conn, period):
    """计算连续 N 个 period 都至少做了 1 道题"""
    fmt = _bucket(period)
    rows = conn.execute(
        f"""SELECT DISTINCT strftime('{fmt}', p.last_at) bucket
            FROM progress p
            WHERE p.last_at IS NOT NULL
            ORDER BY bucket DESC"""
    ).fetchall()
    buckets = {r["bucket"] for r in rows}
    from datetime import datetime, timedelta
    today = datetime.now()
    # 生成从今天往前 60 天/月 的 bucket，逐个看在不在集合里
    streak = 0
    for i in range(365):
        if period == "day":
            d = today - timedelta(days=i)
            bkt = d.strftime("%Y-%m-%d")
        elif period == "week":
            d = today - timedelta(weeks=i)
            bkt = d.strftime("%Y-W%W")
        elif period == "month":
            d = today.replace(day=1)
            from calendar import monthrange
            while i > 0:
                d = (d - timedelta(days=1)).replace(day=1)
                i -= 1
            bkt = d.strftime("%Y-%m")
        else:
            break
        if bkt in buckets:
            streak += 1
        elif i > 0:
            # 中间空了就停（但今天没做不算断）
            break
        else:
            # 今天没做也不算断 streak，从昨天开始算
            continue
    return streak


def generate_advice(conn, period="week"):
    """基于该 period 的数据生成提升建议，返回 list[str]"""
    advices = []
    overall = stats_overall(conn, period)
    modules = stats_by_module(conn, period)
    streak = _count_streak(conn, "day") if period != "month" else 0

    if overall["attempts"] == 0:
        advices.append(f"⚠️ 这个{period_dict(period)}你还没刷题，今天开始吧！")
        return advices

    # 1. 正确率
    if overall["rate"] < 60:
        advices.append(f"🚨 总正确率只有 {overall['rate']:.0f}%，低于 60% 警戒线——建议先放慢速度、看清题干再选。")
    elif overall["rate"] < 75:
        advices.append(f"📉 总正确率 {overall['rate']:.0f}%，还有提升空间——多复盘错题解析。")
    else:
        advices.append(f"✅ 总正确率 {overall['rate']:.0f}%，继续保持！")

    # 2. 薄弱模块（正确率 < 60% 且做题 ≥ 5 道）
    weak = [m for m in modules if m["attempts"] >= 5 and m["rate"] < 60]
    for wm in weak:
        advices.append(
            f"🎯 **{wm['module']}** 正确率仅 {wm['rate']:.0f}%（{wm['attempts']} 题），"
            f"建议集中刷 20 道同模块题、细看解析。"
        )

    # 3. 高频错题模块
    high_wrong = sorted(modules, key=lambda m: m["wrong"], reverse=True)[:2]
    if high_wrong and high_wrong[0]["wrong"] >= 3:
        hw = high_wrong[0]
        advices.append(
            f"🔥 **{hw['module']}** 错题最多（{hw['wrong']} 道），"
            f"用「🔥 错题重练」再过一遍。"
        )

    # 4. 刷题量
    if period == "day":
        if overall["attempts"] < 20:
            advices.append(f"📚 今天只做了 {overall['attempts']} 题，目标建议 ≥ 40 题/天。")
        elif overall["attempts"] >= 60:
            advices.append(f"💪 今天刷了 {overall['attempts']} 题，量够了，记得复盘！")
    elif period == "week":
        if overall["attempts"] < 100:
            advices.append(f"📅 本周只做了 {overall['attempts']} 题，建议每周 ≥ 200 题。")
    elif period == "month":
        if overall["attempts"] < 400:
            advices.append(f"🗓️ 本月只做了 {overall['attempts']} 题，建议每月 ≥ 800 题。")

    # 5. 连续打卡
    if streak >= 7:
        advices.append(f"🔥 连续打卡 **{streak} 天**！坚持就是胜利。")
    elif streak >= 3:
        advices.append(f"✨ 连续打卡 {streak} 天，别断！")
    elif overall["attempts"] > 0 and streak == 0:
        advices.append("⏰ 今天还没刷题，10 分钟就能做 5 道！")

    return advices


def period_dict(period):
    return {"day": "今天", "week": "本周", "month": "本月"}[period]


def export_wrong_markdown(conn, out_path=None):
    """导出错题本为 Markdown，返回实际写的路径"""
    rows = conn.execute(
        """SELECT q.*, p.last_chosen, p.attempts, p.wrong
           FROM questions q
           JOIN progress p ON p.question_id = q.id
           WHERE p.wrong > 0
           ORDER BY q.module, q.year DESC, q.paper, q.seq"""
    ).fetchall()

    if out_path is None:
        out_dir = _app_support_dir()
        from datetime import datetime
        out_path = os.path.join(out_dir, f"错题本-{datetime.now().strftime('%Y%m%d')}.md")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# 公考刷题错题本\n\n")
        f.write(f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
        f.write(f"错题总数：{len(rows)}\n\n")
        f.write("---\n\n")

        cur_module = None
        for q in rows:
            if q["module"] != cur_module:
                cur_module = q["module"]
                f.write(f"\n## {cur_module}\n\n")

            f.write(f"### [{q['year']}] {q['paper']} · {q['module']}/{q['subtype'] or '-'}\n\n")

            if q["shared_passage"]:
                quoted = q["shared_passage"].replace(chr(10), "  \n> ")
                f.write(f"**材料：**\n\n> {quoted}\n\n")

            f.write(f"**题干：** {q['stem']}\n\n")

            for ltr in ("A", "B", "C", "D"):
                opt = q[f"option_{ltr.lower()}"]
                if opt:
                    tag = ""
                    if q["answer"] == ltr:
                        tag = " ✅ 正确答案"
                    if q["last_chosen"] == ltr and q["wrong"] > 0:
                        tag += " ❌ 你选了"
                    f.write(f"- **{ltr}**. {opt}{tag}\n")

            f.write(f"\n**正确答案：** {q['answer']}  ")
            f.write(f"**你的选择：** {q['last_chosen'] or '未作答'}  ")
            f.write(f"**错题次数：** {q['wrong']}/{q['attempts']}\n\n")

            if q["analysis"]:
                quoted = q["analysis"].replace(chr(10), "  \n> ")
                f.write(f"**解析：**\n\n> {quoted}\n\n")

            f.write("---\n\n")

    return out_path
