from typing import Dict, List, Optional, Tuple

from .models import ModInfo, VersionCheckResult
from .modrinth_api import check_mod_version
from .utils import parse_minecraft_version, sort_minecraft_versions


def check_version_compatibility(mods_info: List[ModInfo], test_version: str, loader_type: str) -> VersionCheckResult:
    incompatible_mods: List[Tuple[str, List[str]]] = []
    for mod in mods_info:
        result = check_mod_version(mod.slug, test_version, loader_type)
        if not result.available:
            incompatible_mods.append((mod.name, result.versions))

    return VersionCheckResult(version=test_version, compatible=len(incompatible_mods) == 0, incompatible_mods=incompatible_mods)


def find_next_compatible_version(
    mods_info: List[ModInfo],
    current_version: str,
    loader_type: str,
    allow_downgrade: bool = False,
) -> Tuple[Optional[str], List[VersionCheckResult]]:
    all_versions = set()
    for mod in mods_info:
        all_versions.update(mod.versions)

    sorted_versions = sort_minecraft_versions(list(all_versions))
    current_ver = parse_minecraft_version(current_version)

    if not allow_downgrade:
        sorted_versions = [v for v in sorted_versions if parse_minecraft_version(v) >= current_ver]

    version_checks: List[VersionCheckResult] = []
    for test_version in sorted_versions:
        if test_version == current_version:
            continue
        check_result = check_version_compatibility(mods_info, test_version, loader_type)
        version_checks.append(check_result)
        if check_result.compatible:
            return test_version, version_checks

    return None, version_checks


def check_loader_compatibility(mods: List[Dict[str, str]], version: str, loader: str) -> Tuple[List[ModInfo], int]:
    results: List[ModInfo] = []
    compatible_count = 0
    for mod in mods:
        result = check_mod_version(mod["slug"], version, loader)
        results.append(result)
        if result.available:
            compatible_count += 1
    return results, compatible_count


def find_best_loader(
    mods: List[Dict[str, str]],
    version: str,
    current_loader: str,
    preferred_loader: Optional[str] = None,
) -> Tuple[str, List[ModInfo], Dict[str, int]]:
    all_loaders = {"fabric", "forge", "neoforge", "quilt"}
    loader_stats: Dict[str, int] = {}
    best_loader = current_loader
    best_count = 0
    best_results: List[ModInfo] = []

    for loader in all_loaders:
        results, compatible_count = check_loader_compatibility(mods, version, loader)
        loader_stats[loader] = compatible_count

        is_better = False
        if compatible_count > best_count:
            is_better = True
        elif compatible_count == best_count:
            if loader == current_loader:
                is_better = True
            elif preferred_loader and loader == preferred_loader:
                is_better = True
        if is_better:
            best_count = compatible_count
            best_loader = loader
            best_results = results

    return best_loader, best_results, loader_stats


def find_common_version(mods: List[ModInfo]) -> Optional[str]:
    if not mods:
        return None
    mod_versions = [set(mod.versions) for mod in mods if mod.versions]
    if not mod_versions:
        return None
    common_versions = set.intersection(*mod_versions)
    if not common_versions:
        return None
    sorted_versions = sort_minecraft_versions([v for v in common_versions if "w" not in v and "snapshot" not in v])
    return sorted_versions[-1] if sorted_versions else None
