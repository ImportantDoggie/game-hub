import os, json, re, subprocess
from pathlib import Path

def _steam_roots():
    roots = []
    candidates = [
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Steam",
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Steam",
    ]
    for p in candidates:
        if p.exists() and p not in roots:
            roots.append(p)
    return roots

def _parse_vdf_libraries(vdf_path):
    paths = []
    try:
        text = vdf_path.read_text(encoding="utf-8", errors="ignore")
        for match in re.finditer(r'"path"\s*"([^"]+)"', text):
            paths.append(Path(match.group(1).replace("\\\\\\\\", "\\\\")))
    except Exception:
        pass
    return paths

def scan_steam():
    found = []
    for root in _steam_roots():
        libraries = [root]
        vdf = root / "steamapps" / "libraryfolders.vdf"
        libraries += _parse_vdf_libraries(vdf)
        for lib in libraries:
            apps = lib / "steamapps"
            if not apps.exists():
                continue
            for manifest in apps.glob("appmanifest_*.acf"):
                try:
                    text = manifest.read_text(encoding="utf-8", errors="ignore")
                    appid = re.search(r'"appid"\s*"(\d+)"', text).group(1)
                    name = re.search(r'"name"\s*"([^"]+)"', text).group(1)
                    install_match = re.search(r'"installdir"\s*"([^"]+)"', text)
                    process_name = ""
                    if install_match:
                        game_dir = apps / "common" / install_match.group(1)
                        candidates = [x for x in game_dir.glob("*.exe") if not any(
                            word in x.name.lower() for word in ("uninstall", "crash", "redist", "setup", "launcher"))]
                        if candidates:
                            process_name = candidates[0].name
                    found.append({
                        "title": name, "target": f"steam://rungameid/{appid}",
                        "kind": "steam", "process_name": process_name, "source": "Steam"
                    })
                except Exception:
                    continue
    return found

def scan_epic():
    found = []
    base = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    if not base.exists():
        return found
    for manifest in base.glob("*.item"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            title = data.get("DisplayName") or data.get("AppName")
            exe = data.get("LaunchExecutable", "")
            install = data.get("InstallLocation", "")
            target = Path(install) / exe
            if title and target.exists() and target.suffix.lower() == ".exe":
                found.append({
                    "title": title, "target": str(target), "kind": "exe",
                    "process_name": target.name, "source": "Epic Games"
                })
        except Exception:
            continue
    return found

def _resolve_shortcut(path):
    # Resolve .lnk target through Windows Script Host COM using PowerShell.
    script = (
        "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('" +
        str(path).replace("'", "''") + "'); "
        "Write-Output ($s.TargetPath + '|' + $s.Arguments)"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            capture_output=True, text=True, timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
        )
        line = result.stdout.strip().splitlines()
        if result.returncode == 0 and line and "|" in line[-1]:
            target, args = line[-1].split("|", 1)
            return target.strip(), args.strip()
    except Exception:
        pass
    return "", ""

def scan_shortcuts():
    found = []
    locations = [
        Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
        Path.home() / "Desktop",
        Path(os.environ.get("PUBLIC", r"C:\Users\Public")) / "Desktop",
    ]
    seen = set()
    for folder in locations:
        if not folder.exists():
            continue
        for shortcut in folder.rglob("*.lnk"):
            target, args = _resolve_shortcut(shortcut)
            if not target:
                continue
            low = (shortcut.stem + " " + target).lower()
            # Avoid adding common utilities and launcher shortcuts themselves.
            if any(x in low for x in ["uninstall", "readme", "manual", "steam", "epic games launcher", "gog galaxy"]):
                continue
            key = (target.lower(), args.lower())
            if key in seen:
                continue
            seen.add(key)
            found.append({
                "title": shortcut.stem, "target": str(shortcut),
                "kind": "shortcut", "process_name": Path(target).name,
                "source": "Windows shortcut"
            })
    return found

def scan_all():
    merged = []
    seen = set()
    for game in scan_steam() + scan_epic() + scan_shortcuts():
        key = game["target"].lower()
        if key not in seen:
            seen.add(key)
            merged.append(game)
    return merged
