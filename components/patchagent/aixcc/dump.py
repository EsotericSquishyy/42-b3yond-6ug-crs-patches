import argparse
import base64
from hashlib import md5
from pathlib import Path
from typing import Dict, Set

from sqlalchemy import and_, exists

from aixcc.db import BugProfile, Patch, PatchBug, make_session
from aixcc.utils import search_available_patch_query

parser = argparse.ArgumentParser(description="Dump OSV patches")
parser.add_argument("--delete", action="store_true", help="Delete invalid patches")

if __name__ == "__main__":
    args = parser.parse_args()
    patch_dir = Path(__file__).parent.parent / "testcases/osv-patch/data"
    patch_dir.mkdir(exist_ok=True)

    try:
        with make_session() as session:
            for bug_profile in session.query(BugProfile).all():
                if bug_profile.sanitizer_bug_type.startswith("OSV-"):
                    if args.delete:
                        for patch in (
                            session.query(Patch)
                            .filter(
                                Patch.bug_profile_id == bug_profile.id,
                                exists().where(
                                    and_(
                                        PatchBug.patch_id == Patch.id,
                                        PatchBug.repaired == False,
                                    )
                                ),
                            )
                            .all()
                        ):
                            raw_patch = base64.b64decode(patch.patch).decode()
                            osv_path = patch_dir / bug_profile.sanitizer_bug_type
                            filename = osv_path / f"{md5(raw_patch.encode()).hexdigest()}-{patch.model}.diff"

                            if filename.is_file():
                                filename.unlink()

                    for patch in search_available_patch_query(session, bug_profile.id).all():
                        if patch.model != "unknown":
                            raw_patch = base64.b64decode(patch.patch).decode()

                            osv_path = patch_dir / bug_profile.sanitizer_bug_type
                            filename = osv_path / f"{md5(raw_patch.encode()).hexdigest()}-{patch.model}.diff"

                            if filename.is_file():
                                continue

                            if any(osv_path.glob(f"*-{patch.model}.diff")):
                                print(f"Duplicate patch for {osv_path.name}, skip")
                                continue

                            filename.parent.mkdir(exist_ok=True, parents=True)
                            filename.write_text(raw_patch)
    except Exception as e:
        print(f"[{e.__class__.__name__}] Failed to dump patches")

    fixed_osv_map: Dict[str, Set[str]] = {}
    for osv_path in patch_dir.glob("OSV-*"):
        for diff in osv_path.glob("*.diff"):
            _, model = diff.stem.split("-", 1)
            if model not in fixed_osv_map:
                fixed_osv_map[model] = set()
            fixed_osv_map[model].add(osv_path.name)

    models = sorted(fixed_osv_map.keys())
    model_fixed_count = {model: len(fixed_osv_map[model]) for model in models}

    dataset_dir = Path(__file__).parent.parent / "testcases/osv"

    osv_list = []
    for project_path in dataset_dir.iterdir():
        if project_path.is_dir():
            for osv_path in project_path.glob("OSV-*"):
                osv_yaml = osv_path / "osv.yaml"
                if osv_yaml.is_file():
                    osv_id = osv_path.name
                    model_fixed = [osv_id in fixed_osv_map[model] for model in models]
                    osv_list.append((osv_id, model_fixed))

    raw_osv_id_list = [osv_id for osv_id, _ in osv_list]
    if len(raw_osv_id_list) != len(set(raw_osv_id_list)):
        print("Duplicate OSV ID found")
        for osv_id in raw_osv_id_list:
            if raw_osv_id_list.count(osv_id) > 1:
                print(f"Duplicate OSV ID: {osv_id}")
        exit(1)

    osv_list.sort()
    total_osv = len(osv_list)
    total_fixed = 0

    for i in range(0, len(osv_list), 6):
        chunk = osv_list[i : i + 6]
        line = " "
        for osv_id, model_fixed in chunk:
            tag = "".join("✅" if is_fixed else "❌" for is_fixed in model_fixed)
            line += f"{osv_id:15}: {tag}    "
            total_fixed += 1 if any(model_fixed) else 0

        print(line)

    for model, fixed_count in model_fixed_count.items():
        print(f"{model:20}: {fixed_count}/{len(osv_list)} ({fixed_count / len(osv_list) * 100:.1f}%)")
    print(f"Total               : {total_fixed}/{total_osv} ({total_fixed / total_osv * 100:.1f}%)\n")


# AIXCC_DB_URL=postgresql://root:root@localhost:22222/dataisland python -m aixcc.dump
