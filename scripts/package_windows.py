"""Build the self-contained Windows x64 offline installer.
Run with the build machine's Python 3.13 and the project's AI dependencies installed.
Only explicit program files enter the payload; development databases are never copied.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "target" / "windows-package"
PAYLOAD = WORK / "payload"
CACHE = ROOT / "tools" / "windows-package"
OUTPUT = ROOT / "dist"
VERSION = "1.1.1"
ASSETS = {
    "java": {
        "file": "temurin21-jre.zip",
        "url": "https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.13.1%2B2/OpenJDK21U-jre_x64_windows_hotspot_21.0.13.1_2.zip",
        "sha256": "e15ee1e54a5a3b38027a09cedfa87bc3348d7dd3ce50866dd3d9671d7fffc6c1",
    },
    "python": {
        "file": "python-3.13.3-embed-amd64.zip",
        "url": "https://www.python.org/ftp/python/3.13.3/python-3.13.3-embed-amd64.zip",
        "sha256": "59ff76e16e6597de47474fb22be69e7191a89116910d728ab735079b078e52db",
    },
}
COMPILER_URL = "https://github.com/jrsoftware/issrc/releases/download/is-7_1_1/innosetup-7.1.1-x64.exe"


def log(message):
    print(message, flush=True)


def run(arguments, **kwargs):
    log("Running: " + str(arguments[0]))
    subprocess.run([str(value) for value in arguments], check=True, cwd=ROOT, **kwargs)


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url, destination):
    log("Downloading: " + destination.name)
    request = urllib.request.Request(url, headers={"User-Agent": "Shiguang-Windows-Packager/1.1"})
    temporary = destination.with_suffix(destination.suffix + ".download")
    with urllib.request.urlopen(request, timeout=180) as response, temporary.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    temporary.replace(destination)


def cached_asset(asset):
    path = CACHE / asset["file"]
    if not path.is_file():
        download(asset["url"], path)
    if sha256(path) != asset["sha256"]:
        raise RuntimeError("Runtime archive checksum mismatch: " + path.name)
    return path


def extract(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            final = (destination / entry.filename).resolve()
            if not final.is_relative_to(destination.resolve()):
                raise RuntimeError("Archive path escapes destination")
        bundle.extractall(destination)


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_directory(source, destination):
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def copy_dependencies(destination):
    pending = ["torch", "transformers", "fastapi", "uvicorn"]
    found = {}
    for_name = lambda value: value.lower().replace("_", "-")
    while pending:
        name = pending.pop()
        distribution = metadata.distribution(name)
        canonical = for_name(distribution.metadata["Name"])
        if canonical in found:
            continue
        site = Path(distribution.locate_file("")).resolve()
        files = distribution.files
        if not files:
            raise RuntimeError("Distribution has no installed file inventory: " + name)
        copied = 0
        for item in files:
            source = Path(distribution.locate_file(item)).resolve()
            # Console scripts outside site-packages are unnecessary in the private runtime.
            if not source.is_relative_to(site):
                continue
            relative = source.relative_to(site)
            if "__pycache__" in relative.parts or relative.suffix == ".pyc":
                continue
            if source.is_file():
                copy_file(source, destination / relative)
                copied += 1
        found[canonical] = {"version": distribution.version, "files": copied}
        for text in distribution.requires or ():
            requirement = Requirement(text)
            if not requirement.marker or requirement.marker.evaluate({"extra": ""}):
                pending.append(requirement.name)
    return dict(sorted(found.items()))


def prepare_compiler():
    compiler = CACHE / "inno" / "ISCC.exe"
    if not compiler.is_file():
        installer = CACHE / "innosetup-7.1.1-x64.exe"
        if not installer.is_file():
            download(COMPILER_URL, installer)
        # Verify the official publisher signature before running the compiler installer.
        escaped = str(installer).replace("'", "''")
        verify = (
            "$s=Get-AuthenticodeSignature -LiteralPath '" + escaped + "';"
            "if($s.Status -ne 'Valid' -or $s.SignerCertificate.Subject -notmatch 'Pyrsys|Jordan Russell'){exit 1}"
        )
        run(["powershell.exe", "-NoProfile", "-Command", verify])
        run([installer, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
             "/PORTABLE=1", "/DIR=" + str(compiler.parent), "/NOICONS", "/TASKS="])
    return compiler


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true", help="Use the already built Java jar")
    parser.add_argument("--prepare-only", action="store_true", help="Prepare payload without compiling installer")
    parser.add_argument("--compile-only", action="store_true", help="Compile an existing verified payload")
    args = parser.parse_args()
    if sys.platform != "win32" or sys.version_info[:2] != (3, 13) or platform.machine().lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Build on Windows x64 using Python 3.13.")
    CACHE.mkdir(parents=True, exist_ok=True)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if not args.compile_only:
        if not args.skip_build:
            run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ROOT / "scripts/build.ps1"])
        jar = ROOT / "target/lost-found-1.0.0.jar"
        if not jar.is_file() or not (ROOT / "target/dependency").is_dir():
            raise RuntimeError("Build the Java project first.")
        # Deletion is restricted to this tool's generated payload, never the project's data.
        if PAYLOAD.resolve() != (ROOT / "target/windows-package/payload").resolve():
            raise RuntimeError("Unexpected staging destination")
        if PAYLOAD.exists():
            shutil.rmtree(PAYLOAD)
        PAYLOAD.mkdir(parents=True)
        log("Preparing official Java and Python runtimes...")
        java_archive = cached_asset(ASSETS["java"])
        python_archive = cached_asset(ASSETS["python"])
        unpack = WORK / "java-unpack"
        if unpack.exists():
            shutil.rmtree(unpack)
        extract(java_archive, unpack)
        candidates = [path.parent.parent for path in unpack.glob("*/bin/java.exe")]
        if len(candidates) != 1:
            raise RuntimeError("Unexpected Java archive layout")
        shutil.move(str(candidates[0]), PAYLOAD / "java")
        shutil.rmtree(unpack)
        extract(python_archive, PAYLOAD / "python")
        (PAYLOAD / "python/python313._pth").write_text(
            "python313.zip\n.\nLib\\site-packages\nimport site\n", encoding="ascii"
        )
        log("Copying the complete AI dependency closure into the private Python runtime...")
        packages = copy_dependencies(PAYLOAD / "python/Lib/site-packages")
        # App-local MSVC DLLs make the bundled Python/CPU Torch independent of a
        # separately installed Visual C++ runtime. Do not copy .NET CLR variants.
        system = Path(os.environ["SystemRoot"]) / "System32"
        runtime_dlls = []
        for pattern in ("msvcp140*.dll", "vcruntime140*.dll", "concrt140.dll"):
            for source in system.glob(pattern):
                if "clr" not in source.name.lower():
                    copy_file(source, PAYLOAD / "python" / source.name)
                    runtime_dlls.append({"file": source.name, "sha256": sha256(source)})
        if not (PAYLOAD / "python/msvcp140.dll").is_file():
            raise RuntimeError("Build machine is missing the MSVC runtime needed by CPU Torch")
        copy_file(jar, PAYLOAD / "app.jar")
        copy_directory(ROOT / "target/dependency", PAYLOAD / "lib")
        copy_file(ROOT / "ai/service.py", PAYLOAD / "ai/service.py")
        copy_file(ROOT / "ai/requirements.txt", PAYLOAD / "ai/requirements.txt")
        model = ROOT / "models/bge-small-zh-v1.5"
        manifest = json.loads((model / "manifest.json").read_text(encoding="utf-8-sig"))
        for entry in manifest["files"]:
            source = model / entry["name"]
            if not source.resolve().is_relative_to(model.resolve()) or sha256(source) != entry["sha256"]:
                raise RuntimeError("Model file checksum mismatch: " + entry["name"])
        copy_directory(model, PAYLOAD / "models/bge-small-zh-v1.5")
        copy_file(ROOT / "scripts/windows/desktop.ps1", PAYLOAD / "scripts/desktop.ps1")
        copy_file(ROOT / "scripts/seed_demo.py", PAYLOAD / "scripts/seed_demo.py")
        copy_file(ROOT / "docs/手工测试用例.md", PAYLOAD / "docs/手工测试用例.md")
        (PAYLOAD / "初始化测试数据.cmd").write_bytes(b'@echo off\r\n"%~dp0Shiguang.exe" --demo\r\n')
        copy_file(ROOT / "docs/Windows安装说明.txt", PAYLOAD / "安装说明.txt")
        compiler = Path(os.environ["SystemRoot"]) / "Microsoft.NET/Framework64/v4.0.30319/csc.exe"
        run([compiler, "/nologo", "/target:winexe", "/platform:x64", "/codepage:65001",
             "/reference:System.Windows.Forms.dll", "/reference:System.Drawing.dll",
             "/out:" + str(PAYLOAD / "Shiguang.exe"), ROOT / "scripts/windows/Launcher.cs"])
        notices = (
            "Bundled runtimes: Eclipse Temurin JRE 21, CPython 3.13.3, Microsoft Visual C++ runtime DLLs.\n"
            "Java licenses are under java/legal; Python license is python/LICENSE.txt.\n"
            "AI dependencies retain their original *.dist-info license/metadata files.\n"
            "Model: BAAI/bge-small-zh-v1.5; see models/bge-small-zh-v1.5/README.md and manifest.json.\n"
        )
        (PAYLOAD / "THIRD-PARTY-NOTICES.txt").write_text(notices, encoding="utf-8")
        package_manifest = {
            "version": VERSION, "platform": "windows-x64",
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "runtimes": ASSETS, "ai_packages": packages,
            "app_local_msvc": runtime_dlls,
            "jar_sha256": sha256(PAYLOAD / "app.jar"),
            "model_revision": manifest["revision"],
            "source_data_included": False,
        }
        (PAYLOAD / "package-manifest.json").write_text(json.dumps(package_manifest, indent=2, ensure_ascii=False), encoding="utf-8")
        # Never ship databases, credentials, private uploads or local logs.
        prohibited = [path for path in PAYLOAD.rglob("*") if path.is_file() and
                      (path.suffix in (".db", ".sqlite", ".sqlite3", ".log") or path.name == "admin-credentials.txt")]
        if prohibited:
            raise RuntimeError("Unexpected mutable data in payload: " + str(prohibited[0]))
        log("Checking the isolated Python imports...")
        run([PAYLOAD / "python/python.exe", "-I", "-B", "-c",
             "import sys,torch,numpy,transformers,fastapi,uvicorn; "
             "assert sys.flags.isolated and sys.flags.no_user_site; "
             "print('Isolated runtime OK:',sys.version.split()[0],torch.__version__,transformers.__version__)"])
        log("Payload ready: " + str(PAYLOAD))
        if args.prepare_only:
            return
    if not (PAYLOAD / "package-manifest.json").is_file():
        raise RuntimeError("Prepare and verify the payload first.")
    compiler = prepare_compiler()
    log("Compressing the offline installer. This can take several minutes...")
    run([compiler, "--quiet", "/DPayloadDir=" + str(PAYLOAD), "/DOutputDirPath=" + str(OUTPUT),
         ROOT / "scripts/windows/installer.iss"])
    installer = OUTPUT / ("Shiguang-Setup-" + VERSION + "-x64.exe")
    checksum = sha256(installer)
    (OUTPUT / (installer.name + ".sha256")).write_text(checksum + "  " + installer.name + "\n", encoding="ascii")
    copy_file(ROOT / "docs/Windows安装说明.txt", OUTPUT / "安装说明.txt")
    log("Installer ready: " + str(installer))
    log("Size: %.1f MiB" % (installer.stat().st_size / 1024 / 1024))
    log("SHA256: " + checksum)


if __name__ == "__main__":
    try:
        main()
    except Exception as exception:
        log("Packaging failed: " + str(exception))
        raise SystemExit(1)
