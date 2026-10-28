"""自动更新 - 从 GitHub raw 拉 .py 文件覆盖本地
用法：update.check_and_update(VERSION, REPO_URL)
     成功后返回 (需要重启的文件列表, 变更描述)

用户只需要：
  1. 在 GitHub 开个公开 repo（比如叫 gwy-quiz-updates）
  2. 把 .py + version.txt 推上去
  3. 点托盘「检查更新」
"""
import hashlib
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime

# ===== 用户自己改这两个 =====
# 你的 GitHub 用户名
GH_USER = "SherryCal"
# 推代码的 repo 名
GH_REPO = "gwy-quiz-updates"
# 分支（main 或 master）
GH_BRANCH = "main"
# ============================

# raw 内容最新；jsDelivr 的 branch 解析缓存最长 12 小时，只作 raw 不通时的兜底
REPO_BASES = [
    f"https://raw.githubusercontent.com/{GH_USER}/{GH_REPO}/{GH_BRANCH}",
    f"https://cdn.jsdelivr.net/gh/{GH_USER}/{GH_REPO}@{GH_BRANCH}",
]
# 记住第一个可用的镜像，避免每个文件都重试超时
_working_base = None
# 记录最后一次真实错误，方便在界面上显示原因
_last_error = None


def _http_get(path, timeout=6):
    global _working_base, _last_error
    bases = ([_working_base] if _working_base else []) + REPO_BASES
    last_err = None
    for base in bases:
        # TLS 握手偶发超时，每个镜像多试一次
        for attempt in range(2):
            try:
                import net
                with net.urlopen(f"{base}/{path}", timeout=timeout,
                                 headers={"User-Agent": "gwy-quiz-update"}) as r:
                    data = r.read().decode("utf-8", errors="replace")
                _working_base = base
                return data
            except Exception as e:
                last_err = e
                _last_error = f"{base} → {type(e).__name__}: {e}"
                continue
    raise last_err if last_err else RuntimeError("no mirror available")

# 要推到 git 的文件白名单（只 .py + version.txt + requirements.txt）
PUSH_FILES = [
    "main.py", "main_window.py", "popup.py", "quiz_card.py",
    "db.py", "importer.py", "download.py", "update.py", "net.py",
    "version.txt",
]


def _remote_version():
    """拉远程 version.txt"""
    try:
        txt = _http_get("version.txt")
        for line in txt.strip().split("\n"):
            if "=" in line:
                k, v = line.split("=", 1)
                if k.strip().lower() == "version":
                    return v.strip()
        return None
    except Exception:
        return None


def _remote_file_sha(filename):
    """拉远程文件并算 SHA（用于判断有没有变）"""
    try:
        content = _http_get(filename)
        return hashlib.sha256(content.encode("utf-8")).hexdigest(), content
    except Exception:
        return None, None


def _local_sha(path):
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def check_and_update(current_version, progress=None):
    """检查远程有没有更新，有就下载覆盖
    progress 是回调 func(msg: str) 用来给 UI 显示进度
    返回 (needs_restart: bool, message: str)
    """
    if progress:
        progress(f"正在检查远程版本...")

    remote_ver = _remote_version()
    if remote_ver is None:
        detail = _last_error or "未知错误"
        return False, ("无法连接更新服务器\n\n"
                       f"真实错误：{detail}\n\n"
                       "可尝试：换网络 / 开代理 / 使用已下载好的完整安装包。")

    # 版本号格式 YYYYMMDD.HHMM 可直接字符串比较；远程更旧说明镜像缓存落后
    if remote_ver <= current_version:
        return False, f"当前版本已是最新（v{current_version}）"

    base_dir = os.path.dirname(os.path.abspath(__file__))
    needs_restart = []
    changes = []

    for fn in PUSH_FILES:
        if fn == "version.txt":
            continue
        local_path = os.path.join(base_dir, fn)
        local_hash = _local_sha(local_path)
        remote_hash, content = _remote_file_sha(fn)

        if remote_hash is None:
            if progress:
                progress(f"  {fn} — 远程不存在，跳过")
            continue

        if local_hash == remote_hash and os.path.isfile(local_path):
            continue

        # 下载覆盖
        try:
            with open(local_path, "w", encoding="utf-8") as f:
                f.write(content)
            needs_restart.append(fn)
            changes.append(f"  ✓ {fn} 已更新")
            if progress:
                progress(f"  ✓ {fn} 已更新")
        except Exception as e:
            changes.append(f"  ✗ {fn} 更新失败: {e}")
            if progress:
                progress(f"  ✗ {fn} 更新失败: {e}")

    # 写入新版本号
    with open(os.path.join(base_dir, "version.txt"), "w", encoding="utf-8") as f:
        f.write(f"version={remote_ver}\n")

    msg = f"发现新版本 v{remote_ver}，已更新 {len(needs_restart)} 个文件\n"
    msg += "\n".join(changes)
    msg += "\n\n请退出程序后重新打开以应用更新。"
    return bool(needs_restart), msg


def make_version_file():
    """生成 version.txt 内容（作者自己推代码前跑一下）"""
    now = datetime.now().strftime("%Y%m%d.%H%M")
    print(f"version={now}")
    return f"version={now}"


def generate_github_setup_commands():
    """打印终端命令，让作者一次性建好 GitHub repo"""
    user = GH_USER or "<your-github-username>"
    cmds = f"""
# 在终端里依次跑（只跑一次）：

# 1) 安装 gh（如果没装）
brew install gh

# 2) 登录 GitHub（浏览器弹窗授权）
gh auth login

# 3) 在 gwy-quiz 目录建 git，推到 GitHub
cd {os.path.dirname(os.path.abspath(__file__))}
git init
git add main.py main_window.py popup.py quiz_card.py db.py importer.py download.py update.py version.txt
git commit -m "初始提交 v{datetime.now().strftime('%Y%m%d-%H%M')}"
gh repo create {GH_REPO} --public --source=. --remote=origin --push

# 以后每次改完代码，跑：
# python3 update.py  -- 自动更新 version.txt + 提交推送
"""
    return cmds


if __name__ == "__main__":
    # 作者本地用：跑 python3 update.py 会 git add + commit + push
    import subprocess
    base = os.path.dirname(os.path.abspath(__file__))
    vpath = os.path.join(base, "version.txt")

    # 1. 更新版本号
    new_ver = make_version_file()
    with open(vpath, "w") as f:
        f.write(new_ver + "\n")
    print(f"写入 version.txt: {new_ver}")

    # 2. git push
    os.chdir(base)
    subprocess.run(["git", "add"] + PUSH_FILES, check=False)
    subprocess.run(["git", "commit", "-m", f"update v{new_ver}"], check=False)
    subprocess.run(["git", "push"], check=False)

    # 3. 通知 jsDelivr 清缓存，否则朋友那边可能拿到旧文件
    try:
        purge = f"https://purge.jsdelivr.net/gh/{GH_USER}/{GH_REPO}@{GH_BRANCH}/*"
        with urllib.request.urlopen(purge, timeout=25) as r:
            r.read()
        print("jsDelivr 缓存已刷新 ✓")
    except Exception as e:
        print(f"jsDelivr 清缓存失败（不影响推送）: {e}")

    print("推送完成 ✓（如果报 git 错误，先跑 gh auth login + gh repo create 初始化）")
