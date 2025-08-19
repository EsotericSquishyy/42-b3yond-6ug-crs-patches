from typing import Dict, List

import yaml

from aixcc.db import (
    Source,
    SourceTypeEnum,
    Task,
    TaskTypeEnum,
    make_session,
)
from patch_generator.builder import AIXCCBuilder
from patch_generator.builder.utils import download_or_decompress
from patchagent.lang import Lang
from patchagent.parser.sanitizer import Sanitizer

builder_pool: Dict[str, AIXCCBuilder] = {}


def create_builder(task_id: str) -> AIXCCBuilder:
    if task_id not in builder_pool:
        with make_session() as session:
            task = session.query(Task).filter_by(id=task_id).one()
            for source_entry in session.query(Source).filter_by(task_id=task.id, source_type=SourceTypeEnum.repo).all():
                source_path = download_or_decompress(source_entry.url, source_entry.path)
                if (source_path / task.focus).is_dir():
                    break

            fuzz_tooling_entry = session.query(Source).filter_by(task_id=task.id, source_type=SourceTypeEnum.fuzz_tooling).one()
            fuzz_tooling_path = download_or_decompress(fuzz_tooling_entry.url, fuzz_tooling_entry.path)

            diff_path = None
            if task.task_type != TaskTypeEnum.full:
                diff_entry = session.query(Source).filter_by(task_id=task.id, source_type=SourceTypeEnum.diff).one()
                diff_path = download_or_decompress(diff_entry.url, diff_entry.path)

            real_fuzz_tooling_path = None
            for subpath in fuzz_tooling_path.iterdir():
                if subpath.is_dir():
                    real_fuzz_tooling_path = fuzz_tooling_path / subpath.name
                    break

            assert real_fuzz_tooling_path is not None, "Fuzz tooling path is not a directory"
            project_yaml = real_fuzz_tooling_path / "projects" / task.project_name / "project.yaml"
            project_data = yaml.safe_load(project_yaml.read_text())

            lang: Lang = Lang.from_str(project_data["language"])

            supported_sanitizers: List[Sanitizer] = []
            for sanitizer in project_data.get("sanitizers", []):
                if sanitizer == "address":
                    match lang:
                        case Lang.CLIKE:
                            supported_sanitizers.append(Sanitizer.LeakAddressSanitizer)
                        case Lang.JVM:
                            supported_sanitizers.append(Sanitizer.JazzerSanitizer)
                elif sanitizer == "memory":
                    supported_sanitizers.append(Sanitizer.MemorySanitizer)
                elif sanitizer == "undefined":
                    supported_sanitizers.append(Sanitizer.UndefinedBehaviorSanitizer)

            if len(supported_sanitizers) == 0:
                match lang:
                    case Lang.CLIKE:
                        supported_sanitizers.append(Sanitizer.LeakAddressSanitizer)
                    case Lang.JVM:
                        supported_sanitizers.append(Sanitizer.JazzerSanitizer)

            assert len(supported_sanitizers) > 0, "No supported sanitizers found"

            builder = AIXCCBuilder(
                task_id,
                source_path,
                real_fuzz_tooling_path,
                task.focus,
                task.project_name,
                supported_sanitizers,
                diff_path=diff_path,
            )

            builder_pool[task_id] = builder

    return builder_pool[task_id]
