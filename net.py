"""HTTP 工具：兼容 macOS python.org 版未安装根证书的情况

macOS 上从 python.org 装的 Python，如果没跑过
/Applications/Python X.Y/Install Certificates.command，
SSL 会报 CERTIFICATE_VERIFY_FAILED（curl 却能通，因为 curl 用系统证书）。
这里按 certifi → 系统默认 → 不校验 的顺序兜底。
"""
import ssl
import urllib.error
import urllib.request

DEFAULT_UA = "gwy-quiz"

# 是否已经退到不校验模式（只提示一次）
_warned_unverified = False


def _contexts():
    try:
        import certifi
        yield ssl.create_default_context(cafile=certifi.where())
    except Exception:
        pass
    yield None  # 系统默认证书
    yield ssl._create_unverified_context()  # 兜底


def urlopen(url, timeout=10, headers=None):
    global _warned_unverified
    req = urllib.request.Request(url, headers=headers or {"User-Agent": DEFAULT_UA})
    last_err = None
    for ctx in _contexts():
        try:
            if ctx is None:
                return urllib.request.urlopen(req, timeout=timeout)
            if isinstance(ctx, ssl.SSLContext) and ctx.verify_mode == ssl.CERT_NONE:
                if not _warned_unverified:
                    print("[gwy-quiz] 本机 Python 缺少根证书，已降级为不校验证书；"
                          "建议运行 /Applications/Python X.Y/Install Certificates.command")
                    _warned_unverified = True
            return urllib.request.urlopen(req, timeout=timeout, context=ctx)
        except urllib.error.URLError as e:
            if isinstance(getattr(e, "reason", None), ssl.SSLCertVerificationError):
                last_err = e
                continue
            raise
        except ssl.SSLCertVerificationError as e:
            last_err = e
            continue
    raise last_err if last_err else RuntimeError("no TLS context available")
