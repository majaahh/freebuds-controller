#!/usr/bin/env python3
# Copyright (c) 2026 Majaahh
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
import gzip
import json
import logging
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path
from typing import Optional

log = logging.getLogger("plugin-download")


class _PlainFormatter(logging.Formatter):
    _PREFIX = {
        logging.WARNING: "WARNING: ",
        logging.ERROR: "ERROR: ",
        logging.CRITICAL: "CRITICAL: ",
    }

    def format(self, record):
        return self._PREFIX.get(record.levelno, "") + record.getMessage()


REGIONS = {
    "dr3": {
        "name": "Europe",
        "cdn": "https://contentcenter-dre.dbankcdn.cn/cch5/AILife/eu",
    },
    "dr1": {"name": "China", "cdn": "https://smarthome-drcn.dbankcdn.com"},
    "dr2": {
        "name": "Asia/Africa/LatAm",
        "cdn": "https://contentcenter-dra.dbankcdn.cn/cch5/AILife/ra",
    },
    "dr4": {
        "name": "Russia",
        "cdn": "https://contentcenter-drru.dbankcdn.ru/cch5/AILife/ru",
    },
}

ALL_REGIONS = ("dr3", "dr1", "dr2", "dr4")

ENVIRONMENTS = (
    "device/guide",  # DEVICE_GUIDE_ENVIRONMENT (default)
    "device/release",  # DEVICE_RELEASE_ENVIRONMENT (CN / oversea commercial)
    "device/release_oversea",  # DEVICE_RELEASE_ENVIRONMENT_OVERSEA (Europe)
    "device/release_asia",  # DEVICE_RELEASE_ENVIRONMENT_ASIA
    "device/release_russian",  # DEVICE_RELEASE_ENVIRONMENT_RUSSIAN
    "device/release_my",  # DEVICE_RELEASE_ENVIRONMENT_MY
    "device/guide_oversea",
    "device/guide_asia",
    "device/guide_russian",
    "device/guide_my",
    "device/debug",
    "device/debug_oversea",
    "device/debug_asia",
    "device/debug_russian",
    "device/debug_my",
)

PLUGIN_ID = "smartAudioPlugin"
PLUGIN_PATH = "aiLifePlugins/smartAudioPlugin"
DEFAULT_FILE_NAME = "com.huawei.smartaudioplugin.jar"

DEFAULT_ENV = "device/guide"  # DEVICE_GUIDE_ENVIRONMENT

METADATA_FILES = (
    "pluginConfig.json",
    "pluginConfigV3.json",
    "pluginInfo.json",
    "pluginInfoV2.json",
    "pluginInfoV3.json",
    "pluginVersion.json",
    "version.json",
    "supportDeviceList.json",
)
PLUGIN_INFO_PRIORITY = ("pluginInfoV3.json", "pluginInfoV2.json", "pluginInfo.json")
VERSION_FILE = "version.json"

DEFAULT_UA = (
    "Mozilla/5.0 (Linux; Android 13; LYA-L29 Build/HUAWEILYA-L29) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 "
    "Chrome/99.0.0.0 Mobile Safari/537.36"
)

TIMEOUT = 30
RETRIES = 2


def _request(url: str, method: str, read_body: bool = True) -> tuple:
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept-Encoding": "identity",
        "Connection": "close",
    }
    req = urllib.request.Request(url, method=method, headers=headers)
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                body = resp.read() if read_body else b""
                return resp.status, dict(resp.headers), body
        except urllib.error.HTTPError as e:
            try:
                body = e.read() if read_body else b""
            except Exception:
                body = b""
            return e.code, dict(e.headers), body
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < RETRIES:
                log.debug(f"retry {attempt}/{RETRIES} for {url} ({e})")
                time.sleep(0.5 * attempt)
    return None, {}, b""


def head(url: str) -> tuple:
    return _request(url, "HEAD", read_body=False)


def get(url: str) -> tuple:
    return _request(url, "GET", read_body=True)


def _decompress(headers: dict, body: bytes) -> bytes:
    enc = headers.get("Content-Encoding", "").lower()
    try:
        if enc == "gzip":
            return gzip.decompress(body)
        if enc == "deflate":
            try:
                return zlib.decompress(body)
            except zlib.error:
                return zlib.decompress(body, -zlib.MAX_WBITS)
    except (zlib.error, OSError) as e:
        log.warning(f"failed to decompress {enc} response: {e}")
    return body


def _extract_plugin_infos(obj) -> list:
    found = []
    if isinstance(obj, dict):
        if (
            "fileName" in obj
            or "versionCode" in obj
            or "version" in obj
            or "proId" in obj
        ):
            found.append(obj)
        for v in obj.values():
            found.extend(_extract_plugin_infos(v))
    elif isinstance(obj, list):
        for v in obj:
            found.extend(_extract_plugin_infos(v))
    return found


def parse_plugin_info(raw: bytes) -> list:
    try:
        data = json.loads(raw)
    except (ValueError, TypeError) as e:
        log.warning(f"plugin info is not valid JSON: {e}")
        return []
    infos = _extract_plugin_infos(data)
    audio = [
        i for i in infos if "smartaudioplugin" in str(i.get("fileName", "")).lower()
    ]
    return audio + [i for i in infos if i not in audio]


def _info_fields(info: dict) -> dict:
    return {
        "productId": info.get("proId") or info.get("productId"),
        "packageName": info.get("packageName"),
        "pluginPath": info.get("pluginPath"),
        "fileName": info.get("fileName") or DEFAULT_FILE_NAME,
        "version": info.get("version"),
        "versionCode": info.get("versionCode"),
        "url": info.get("url") or info.get("pluginUrl") or info.get("downloadUrl"),
    }


def build_jar_urls(cdn_root: str, env: str, info: dict, version_code=None) -> list:
    fields = _info_fields(info)
    file_name = fields["fileName"] or DEFAULT_FILE_NAME

    explicit = fields["url"] or fields["pluginPath"]
    if isinstance(explicit, str) and "://" in explicit:
        return [explicit]

    versions = []
    if fields["version"] not in (None, "", 0):
        versions.append(str(fields["version"]))
    vc = version_code if version_code is not None else fields["versionCode"]
    if vc not in (None, "", 0):
        versions.append(str(vc))

    paths = [fields["productId"], PLUGIN_PATH, PLUGIN_ID]
    if fields["pluginPath"]:
        paths.insert(0, fields["pluginPath"].strip("/"))

    urls = []
    root = f"{cdn_root}/{env}"
    for path in dict.fromkeys(filter(None, paths)):
        base = f"{root}/{path.strip('/')}/plugin"
        for v in dict.fromkeys(versions):
            urls.append(f"{base}/{v}/{file_name}")
        if not versions:
            urls.append(f"{base}/{file_name}")
    return list(dict.fromkeys(urls))


def build_output_name(info: dict, version_name=None, version_code=None) -> str:
    fields = _info_fields(info)
    base = fields["packageName"]
    if not base:
        base = (fields["fileName"] or DEFAULT_FILE_NAME).rsplit(".", 1)[0]
    ver = version_name or fields["version"] or version_code or fields["versionCode"]
    return f"{base}@{ver}.apk" if ver else f"{base}.apk"


def probe_region(cdn_root: str, envs) -> dict:
    results = {}
    for env in envs:
        per_file = {}
        for f in METADATA_FILES:
            url = f"{cdn_root}/{env}/{PLUGIN_PATH}/plugin/{f}"
            status, headers, _ = head(url)
            if status in (400, 405):
                status, headers, _ = get(url)
            per_file[f] = (status, headers)
            log.debug(f"HEAD {url} -> {status}")
        results[env] = per_file
    return results


def download_metadata(
    cdn_root: str, env: str, out_dir: Path, keep_json: bool = False
) -> dict:
    saved = {}
    for f in METADATA_FILES:
        url = f"{cdn_root}/{env}/{PLUGIN_PATH}/plugin/{f}"
        status, headers, body = get(url)
        if status == 200 and body:
            body = _decompress(headers, body)
            if keep_json:
                (out_dir / f).write_bytes(body)
            saved[f] = body
        else:
            log.debug(f"  {f:<28} -> {status if status else 'unreachable'}")
    return saved


def _filename_from_response(headers: dict, final_url: str, fallback: str) -> str:
    cd = headers.get("Content-Disposition", "")
    m = re.search(r'filename="([^"]+)"', cd) or re.search(r"filename=([^;]+)", cd)
    if m:
        return m.group(1).strip()
    name = urllib.parse.urlparse(final_url).path.rsplit("/", 1)[-1]
    if name and "." in name:
        return urllib.parse.unquote(name)
    return fallback


def _progress_bar(downloaded: int, total):
    if total:
        pct = downloaded * 100 // total
        bar = "#" * (40 * downloaded // total)
        bar += "-" * (40 - len(bar))
        sys.stderr.write(
            f"\r{pct:3d}% [{bar}] {downloaded / 1048576:.1f}/{total / 1048576:.1f} MiB"
        )
    else:
        sys.stderr.write(f"\r{downloaded / 1048576:.1f} MiB")
    sys.stderr.flush()


def _stream_download(
    url: str, dest: Path, fallback_name: str, progress=None
) -> Optional[tuple]:
    headers = {
        "User-Agent": DEFAULT_UA,
        "Accept-Encoding": "identity",
        "Connection": "close",
    }
    req = urllib.request.Request(url, method="GET", headers=headers)
    for attempt in range(1, RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                final_url = resp.geturl()
                name = _filename_from_response(resp.headers, final_url, fallback_name)
                log.info(f"Downloading {name} from {url}")
                try:
                    total = int(resp.headers.get("Content-Length"))
                except (TypeError, ValueError):
                    total = None
                downloaded = 0
                with open(dest, "wb") as fh:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        fh.write(chunk)
                        downloaded += len(chunk)
                        if progress:
                            progress(downloaded, total)
                return final_url, name
        except urllib.error.HTTPError:
            return None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            if attempt < RETRIES:
                log.debug(f"retry {attempt}/{RETRIES} for {url} ({e})")
                time.sleep(0.5 * attempt)
    dest.unlink(missing_ok=True)
    return None


def download_jar(urls: list, out_dir: Path, fallback_name: str) -> Optional[Path]:
    for url in urls:
        log.debug(f"  GET {url}")
        tmp = out_dir / f"{fallback_name}.part"
        result = _stream_download(url, tmp, fallback_name, progress=_progress_bar)
        if result is None:
            log.debug("    -> unreachable")
            continue
        _, name = result
        sys.stderr.write("\n")
        path = out_dir / name
        tmp.replace(path)
        return path
    return None


def run(args):
    regions = list(ALL_REGIONS) if args.region == "all" else [args.region]
    if args.env == "all":
        envs = list(ENVIRONMENTS)
    elif args.env is None:
        envs = [DEFAULT_ENV]
    else:
        envs = [args.env]
    any_found = False

    for rk in regions:
        region = REGIONS[rk]
        cdn = region["cdn"]
        out_dir = Path(args.out_dir)
        log.info(f"Connecting to {region['name']} server ({cdn})")

        probe = probe_region(cdn, envs)
        if args.probe_only:
            for e in envs:
                line = ", ".join(f"{f}={s or 'x'}" for f, (s, _) in probe[e].items())
                log.info(f"  {e:<18} {line}")
            if any(s == 200 for e in envs for s, _ in probe[e].values()):
                any_found = True
            continue
        if not any(s == 200 for e in envs for s, _ in probe[e].values()):
            log.warning("  no metadata reachable under any environment")
            continue
        out_dir.mkdir(parents=True, exist_ok=True)

        for env in envs:
            if not any(s == 200 for s, _ in probe[env].values()):
                log.info(f"env {env:<18} is unreachable")
                continue
            log.info(f"Using env {env}")
            saved = download_metadata(cdn, env, out_dir, args.keep_json)
            if not saved:
                continue
            any_found = True
            if args.metadata_only:
                for f, body in saved.items():
                    log.info(f"{f}:\n{body.decode('utf-8', errors='replace')}")
                continue
            info = {}
            for f in PLUGIN_INFO_PRIORITY:
                if f in saved:
                    candidates = parse_plugin_info(saved[f])
                    if candidates:
                        info = candidates[0]
                        break

            version_name = None
            version_code = None
            if VERSION_FILE in saved:
                try:
                    v = json.loads(saved[VERSION_FILE])
                    version_name = v.get("versionName")
                    version_code = v.get("versionCode")
                except (ValueError, TypeError) as e:
                    log.warning(f"cannot parse {VERSION_FILE}: {e}")

            urls = build_jar_urls(cdn, env, info, version_code)
            if not urls:
                log.warning("  cannot construct the plugin URL")
                continue
            file_name = build_output_name(info, version_name, version_code)
            jar_path = download_jar(urls, out_dir, file_name)
            if not jar_path:
                log.warning("  no candidate URL returned the plugin file")

    if not any_found:
        log.warning("No metadata or plugin file was reachable from any region.")
        return 1
    return 0


def build_argparser():
    p = argparse.ArgumentParser(
        description="Download the Huawei Smart Audio Plugin "
        "(com.huawei.smartaudioplugin) from the per-region AI Life "
        "CDN / AppGallery.",
    )
    p.add_argument(
        "--region", choices=["all", "dr3", "dr1", "dr2", "dr4"], default="dr3"
    )
    p.add_argument(
        "--env",
        choices=["all", *ENVIRONMENTS],
        default=DEFAULT_ENV,
        help=(
            "environment path to use; 'all' runs every environment "
            f"(default: {DEFAULT_ENV})"
        ),
    )
    p.add_argument("-o", dest="out_dir", default=".")
    p.add_argument("--probe-only", action="store_true")
    p.add_argument("--metadata-only", action="store_true")
    p.add_argument("--keep-json", action="store_true")
    p.add_argument("--debug", action="store_true")
    return p


def main(argv=None):
    args = build_argparser().parse_args(argv)
    root = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(_PlainFormatter())
    root.handlers[:] = [handler]
    root.setLevel(logging.DEBUG if args.debug else logging.INFO)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
