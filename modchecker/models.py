from dataclasses import dataclass
from typing import List, Optional, Set, Tuple


@dataclass
class VersionCheckResult:
    version: str
    compatible: bool
    incompatible_mods: List[Tuple[str, List[str]]]  # (mod_name, available_versions)


@dataclass
class ModInfo:
    name: str
    slug: str
    url: str
    versions: List[str]
    available: bool
    version_id: Optional[str] = None
    loader_types: Optional[Set[str]] = None
    download_url: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None
