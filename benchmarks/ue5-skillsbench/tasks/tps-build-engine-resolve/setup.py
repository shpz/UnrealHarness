"""Setup: Convert EngineAssociation from launcher version to GUID for source-built lookup."""
import sys
import uuid
import winreg
from pathlib import Path
import json


def main():
    project_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".").resolve()
    uproject_path = project_path / "TPSample.uproject"

    if not uproject_path.exists():
        raise RuntimeError(f".uproject not found: {uproject_path}")

    uproject = json.loads(uproject_path.read_text(encoding="utf-8"))
    engine_association = uproject.get("EngineAssociation", "")

    # If already a GUID, preserve it (source-built engine already uses GUID)
    if not engine_association or len(engine_association) > 10:
        print(f"EngineAssociation already looks like a GUID or is empty: {engine_association}")
        print("No setup changes needed.")
        return

    # Convert version number (e.g. "5.7") to a GUID and register in HKCU
    new_guid = str(uuid.uuid4())
    uproject["EngineAssociation"] = new_guid
    uproject_path.write_text(json.dumps(uproject, indent=2), encoding="utf-8")
    print(f"Changed EngineAssociation from '{engine_association}' to GUID '{new_guid}'")

    # Find the actual engine path from the original registry entry
    engine_path = None
    for hive, key_fmt in [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\Unreal Engine\{}"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\EpicGames\Unreal Engine\{}"),
    ]:
        try:
            with winreg.OpenKey(hive, key_fmt.format(engine_association)) as key:
                value, _ = winreg.QueryValueEx(key, "InstalledDirectory")
                if value and Path(value).exists():
                    engine_path = value
                    break
        except OSError:
            continue

    if not engine_path:
        # Fallback: look for a source-built engine in the registry
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"SOFTWARE\Epic Games\Unreal Engine\Builds") as builds_key:
                i = 0
                while True:
                    try:
                        sub_name = winreg.EnumKey(builds_key, i)
                        with winreg.OpenKey(builds_key, sub_name) as sub_key:
                            value, _ = winreg.QueryValueEx(sub_key, "Path")
                            if value and Path(value).exists():
                                engine_path = value
                                break
                    except OSError:
                        break
                    i += 1
        except OSError:
            pass

    if not engine_path:
        raise RuntimeError("Could not find engine path from registry. Please verify UE5 installation.")

    # Register the new GUID in HKCU
    reg_path = rf"SOFTWARE\Epic Games\Unreal Engine\Builds\{new_guid}"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_SZ, str(engine_path))
        print(f"Registered GUID in HKCU\\{reg_path} -> {engine_path}")
    except OSError as e:
        raise RuntimeError(f"Failed to write registry: {e}")


if __name__ == "__main__":
    main()
