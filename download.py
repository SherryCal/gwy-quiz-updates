"""下载 xingcezhenti 仓库 markdown - 用 HTML 网页抓目录，raw.githubusercontent.com 下载"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "repo")
REPO = "ERRRC/xingcezhenti"
BRANCH = "main"
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

# 6 个主目录（按仓库实际命名）
MODULES = [
    "01-政治理论",
    "02-常识判断",
    "03-言语理解与表达",
    "04-数量关系",
    "05-判断推理",
    "06-资料分析",
]

def fetch_html(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")

def list_md_files_in_dir(dir_path):
    """抓一个目录下所有 .md 文件名（处理分页）"""
    files = []
    page = 1
    while True:
        suffix = f"?per_page=100&page={page}" if page > 1 else "?per_page=100"
        url = f"https://github.com/{REPO}/tree/{BRANCH}/{urllib.parse.quote(dir_path)}{suffix}"
        html = fetch_html(url)
        # 匹配 blob 链接
        matches = re.findall(
            rf'href="/{REPO}/blob/{BRANCH}/([^"]+\.md)"', html)
        matches = list(dict.fromkeys(matches))   # 去重保序
        if not matches:
            break
        files.extend(matches)
        if len(matches) < 100:
            break
        page += 1
        time.sleep(0.5)
    return files

def download_one(path):
    url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{urllib.parse.quote(path)}"
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()

def build_file_list():
    """遍历 6 个模块，收集所有 md 路径"""
    cache = os.path.join(DEST, "..", ".tree.json")
    if os.path.exists(cache):
        with open(cache) as f:
            return json.load(f)
    all_files = []
    for mod in MODULES:
        print(f"  抓取 {mod} ...")
        files = list_md_files_in_dir(mod)
        all_files.extend(files)
        print(f"    -> {len(files)} 个 md")
        time.sleep(0.3)
    print(f"  总计 {len(all_files)} 个 md")
    with open(cache, "w") as f:
        json.dump(all_files, f)
    return all_files

def download_all(limit=None):
    os.makedirs(DEST, exist_ok=True)
    files = build_file_list()
    if limit:
        files = files[:limit]
    print(f"开始下载 {len(files)} 个文件到 {DEST}")

    done = skip = fail = 0
    for i, path in enumerate(files, 1):
        local = os.path.join(DEST, path)
        os.makedirs(os.path.dirname(local), exist_ok=True)
        if os.path.exists(local) and os.path.getsize(local) > 1000:
            skip += 1; continue
        try:
            data = download_one(path)
            with open(local, "wb") as out:
                out.write(data)
            done += 1
        except Exception as e:
            fail += 1
            if fail <= 3:
                print(f"  [失败] {path}: {e}")
        if i % 100 == 0 or i == len(files):
            print(f"  [{i}/{len(files)}] 新下 {done} 跳过 {skip} 失败 {fail}")
        time.sleep(0.1)
    print(f"完成：新下载 {done}，跳过 {skip}，失败 {fail}")


if __name__ == "__main__":
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    download_all(limit)
