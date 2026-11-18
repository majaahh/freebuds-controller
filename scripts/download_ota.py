#!/usr/bin/env python3
# Copyright (c) 2026 Majaahh
# SPDX-License-Identifier: GPL-3.0-or-later

import argparse
from contextlib import closing
import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree


def huawei_url(url):
    parts = urlsplit(url)
    domains = (
        "hicloud.com",
        "dbankcdn.com",
        "dbankcdn.cn",
        "dbankcdn.ru",
        "dbankcloud.com",
        "dbankcloud.cn",
        "huawei.com",
    )
    if (
        parts.scheme not in ("http", "https")
        or parts.username is not None
        or parts.password is not None
        or parts.port not in (None, 443)
        or not any(
            parts.hostname == d or (parts.hostname or "").endswith("." + d)
            for d in domains
        )
    ):
        raise ValueError("Expected a Huawei firmware service or CDN URL")
    return parts._replace(scheme="https").geturl()


class HuaweiRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, huawei_url(newurl))


http = build_opener(HuaweiRedirect())


def saved_manifest(database, version_id):
    with closing(
        sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    ) as db:
        rows = db.execute(
            "SELECT VERSION_ID, VERSION, ZIP_NAME, CHANGELOG_DOWNLOAD_URL FROM DB_VERSION_INFO "
            "WHERE CHANGELOG_DOWNLOAD_URL IS NOT NULL AND CHANGELOG_DOWNLOAD_URL != '' "
            "ORDER BY VERSION_ID DESC"
        ).fetchall()
    if not rows:
        raise ValueError("This AI Life database has no saved firmware URLs")
    if version_id is None:
        for record_id, version, name, _ in rows:
            print(f"{record_id}  {version}  {name or ''}")
        print("Select the 5i build with --version-id ID.")
        return None
    for record_id, version, _, url in rows:
        if record_id == version_id:
            print("Saved version", version)
            return manifest_url(url)
    raise ValueError(f"No saved firmware URL for version ID {version_id}")


def manifest_url(url):
    parts = urlsplit(huawei_url(url))
    folder, _, name = parts.path.rpartition("/")
    if name not in ("changelog.xml", "filelist.xml") or not folder.endswith("/full"):
        raise ValueError(
            "Expected the full/filelist.xml or full/changelog.xml URL from AI Life"
        )
    return parts._replace(path=folder + "/filelist.xml", fragment="").geturl()


def connected_5i():
    result = subprocess.run(
        ["bluetoothctl", "devices", "Connected"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    addresses = []
    for line in result.stdout.splitlines():
        fields = line.split(maxsplit=2)
        if (
            len(fields) == 3
            and fields[0] == "Device"
            and "freebuds 5i" in fields[2].lower()
        ):
            addresses.append(fields[1])
    if len(addresses) != 1:
        raise ValueError("Connect one FreeBuds 5i to this host or specify --device MAC")
    return addresses[0]


def read_identity(address, read_serial):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from freebuds_controller import FreeBudsController, parse_tlv

    controller = FreeBudsController()
    tags = [7, 15]
    if read_serial:
        tags.append(9)
    request = bytes([1, 7] + [n for tag in tags for n in (tag, 0)])
    fields = {}
    try:
        if not controller.connect(address):
            raise ValueError("Could not open the FreeBuds Bluetooth serial port")
        for frame in controller.send_command(request):
            if frame["svc"] == 1 and frame["cmd"] == 7:
                for tlv in parse_tlv(frame["data"]):
                    if tlv["tag"] in tags:
                        fields[tlv["tag"]] = (
                            tlv["value"].rstrip(b"\0").decode("ascii").strip()
                        )
    finally:
        controller.disconnect()
    if not all(fields.get(tag) for tag in tags):
        raise ValueError("Device did not report all requested OTA identity fields")
    return fields[15], fields[7], fields.get(9, "")


def query(package, firmware, region, serial=""):
    rules = dict(
        deviceName="Huawei" + package,
        packageName="com.huawei." + package,
        deviceId=serial,
        packageType="full",
        packageVersionCode=firmware,
        firmware=firmware,
        os="smarthome",
    )
    url = f"https://update-{region}.platform.hicloud.com/smartAccessory/v2/Check.action?latest=true&defenceHijack=true"
    req = Request(
        url,
        data=json.dumps({"rules": rules}).encode(),
        headers={"Content-Type": "application/json;charset=UTF-8"},
    )
    with http.open(req, timeout=30) as response:
        result = json.load(response)
    status = str(result.get("status"))
    if status == "1" and not result.get("components"):
        return None
    if status not in ("0", "1") or not result.get("components"):
        raise ValueError(f"Huawei returned status {status} without a usable update")
    return result["components"][0]


def download(manifest_address, directory):
    parts = urlsplit(manifest_url(manifest_address))
    with http.open(parts.geturl(), timeout=30) as response:
        manifest = ElementTree.parse(response)
    for entry in manifest.iter("file"):
        name = (entry.findtext("spath") or "").strip()
        if not name.endswith(".zip"):
            continue
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Invalid firmware filename")
        checks = {
            alg: entry.findtext(alg, "").strip().lower() for alg in ("sha256", "md5")
        }
        checks = {alg: digest for alg, digest in checks.items() if digest}
        if not checks:
            raise ValueError("Missing firmware checksum")
        size = int(entry.findtext("size"))
        directory.mkdir(parents=True, exist_ok=True)
        dest = directory / path.name
        with tempfile.TemporaryDirectory(dir=directory) as scratch:
            tmp = Path(scratch) / "download"
            with (
                http.open(
                    parts._replace(
                        path=parts.path.rpartition("/")[0] + "/" + quote(name)
                    ).geturl(),
                    timeout=60,
                ) as response,
                tmp.open("wb") as out,
            ):
                shutil.copyfileobj(response, out)
            if tmp.stat().st_size != size:
                raise ValueError("Firmware size mismatch")
            for alg, expected in checks.items():
                with tmp.open("rb") as stream:
                    if hashlib.file_digest(stream, alg).hexdigest() != expected:
                        raise ValueError(f"Firmware {alg} mismatch")
            with zipfile.ZipFile(tmp) as archive:
                members = [
                    m for m in archive.infolist() if m.filename.lower().endswith(".bin")
                ]
                if not members:
                    raise ValueError("Firmware ZIP contains no .bin")
                for member in members:
                    state = (
                        "encrypted ZIP entry"
                        if member.flag_bits & 1
                        else "unencrypted ZIP entry"
                    )
                    print(f"{member.filename} ({member.file_size} bytes, {state})")
            tmp.replace(dest)
        return dest
    raise ValueError("Manifest has no full firmware ZIP")


def main():
    parser = argparse.ArgumentParser(
        description="Download the full OTA offered to a FreeBuds device. Device mode sends the serial to Huawei unless --anonymous is used."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--device",
        nargs="?",
        const="auto",
        metavar="MAC",
        help="Read OTA identity from connected FreeBuds (default: auto-detect)",
    )
    identity = parser.add_mutually_exclusive_group()
    identity.add_argument(
        "--serial", help="Device serial to send only to Huawei for the OTA check"
    )
    identity.add_argument(
        "--anonymous", action="store_true", help="Skip reading and sending the serial"
    )
    parser.add_argument(
        "--redownload",
        action="store_true",
        help="Request the installed release using an earlier build as the comparison baseline",
    )
    source.add_argument("--package", help="Check for an OTA using device info tag 0x0F")
    source.add_argument(
        "--manifest-url",
        help="Official full/filelist.xml or full/changelog.xml from AI Life",
    )
    source.add_argument(
        "--ai-life-db",
        type=Path,
        help="Local copy of audio_device_kit.db; lists cached releases by default",
    )
    parser.add_argument(
        "--version-id", type=int, help="Download this release from --ai-life-db"
    )
    parser.add_argument("--firmware", help="Installed software version from tag 0x07")
    parser.add_argument(
        "--region", choices=("dre", "drcn", "dra", "drru", "drsx"), default="dre"
    )
    parser.add_argument("-o", type=Path, default=Path.cwd(), metavar="DIR")
    args = parser.parse_args()
    if bool(args.package) != bool(args.firmware):
        parser.error("--package and --firmware must be supplied together")
    if args.version_id is not None and not args.ai_life_db:
        parser.error("--version-id requires --ai-life-db")
    if (args.manifest_url or args.ai_life_db) and (
        args.serial or args.anonymous or args.redownload
    ):
        parser.error(
            "Device identity and --redownload apply only to Huawei update checks"
        )
    try:
        if args.ai_life_db:
            url = saved_manifest(args.ai_life_db, args.version_id)
            if url is None:
                return
        elif args.manifest_url:
            url = args.manifest_url
        else:
            serial = args.serial or ""
            if args.package:
                package, installed = args.package, args.firmware
            else:
                address = (
                    args.device if args.device not in (None, "auto") else connected_5i()
                )
                package, installed, device_serial = read_identity(
                    address, not (args.serial or args.anonymous)
                )
                serial = serial or device_serial
            baseline = installed
            if args.redownload:
                match = re.fullmatch(r"(.*\.)(\d+)(\([^()]+\))", installed)
                if not match or int(match[2]) == 0:
                    raise ValueError(
                        "Cannot derive an earlier baseline for this version format"
                    )
                if (
                    package == "BTFT0014"
                    and installed == "HarmonyOS 2.1.0.218(F001H003C00)"
                ):
                    baseline = "HarmonyOS 2.1.0.202(F001H003C00)"
                else:
                    baseline = f"{match[1]}{int(match[2]) - 1}{match[3]}"
            print(
                f"Checking {package}, installed {installed}, via Huawei {args.region}",
                flush=True,
            )
            component = query(package, baseline, args.region, serial)
            if component is None:
                sys.exit("Huawei returned no package URL for this request.")
            if args.redownload:
                version = (
                    str(component.get("version", "")).removeprefix("HarmonyOS ").strip()
                )
                if version != installed.removeprefix("HarmonyOS ").strip():
                    raise ValueError(
                        f"Huawei offered {version}, not the requested installed release"
                    )
            print("Offered version", component.get("version"))
            base = urlsplit(component["url"])
            url = base._replace(
                path=base.path.rstrip("/") + "/full/filelist.xml"
            ).geturl()
        print(download(url, args.o))
    except (
        OSError,
        sqlite3.Error,
        subprocess.SubprocessError,
        ValueError,
        KeyError,
        TypeError,
        zipfile.BadZipFile,
        ElementTree.ParseError,
    ) as exc:
        sys.exit(f"OTA download failed: {exc}")


if __name__ == "__main__":
    main()
