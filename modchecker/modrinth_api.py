from typing import Dict, List, Optional, Set
import requests

from .cache import cache
from .models import ModInfo
from .utils import parse_minecraft_version


def check_mod_version(slug: str, target_version: str, loader_type: str) -> ModInfo:
    cached_data = cache.get_cached_data(slug, target_version, loader_type)
    if cached_data:
        return ModInfo(**cached_data)

    try:
        all_data = cache.get_all_data(slug)
        if not all_data:
            url = f"https://api.modrinth.com/v2/project/{slug}/version"
            response = cache.make_request(url)
            response.raise_for_status()
            versions = response.json()

            project_url = f"https://api.modrinth.com/v2/project/{slug}"
            project_response = cache.make_request(project_url)
            project_response.raise_for_status()
            project_data = project_response.json()

            cache.cache_all_data(slug, {"project": project_data, "versions": versions})
        else:
            project_data = all_data["project"]
            versions = all_data["versions"]

        mod_info = ModInfo(
            name=project_data["title"],
            slug=slug,
            url=f"https://modrinth.com/mod/{slug}",
            versions=[],
            available=False,
        )

        compatible_version = None
        for ver in versions:
            if loader_type in ver["loaders"] and target_version in ver["game_versions"]:
                compatible_version = ver
                break
            mod_info.versions.extend(ver["game_versions"])
            mod_info.loader_types = mod_info.loader_types or set()
            mod_info.loader_types.update(ver["loaders"])

        if compatible_version:
            mod_info.available = True
            mod_info.version_id = compatible_version["id"]
            mod_info.download_url = compatible_version["files"][0]["url"]
            mod_info.filename = compatible_version["files"][0]["filename"]

        mod_info.versions = list(set(mod_info.versions))
        mod_info.versions.sort(key=lambda x: parse_minecraft_version(x), reverse=True)

        cache.cache_data(
            slug,
            target_version,
            loader_type,
            {
                "name": mod_info.name,
                "slug": mod_info.slug,
                "url": mod_info.url,
                "versions": mod_info.versions,
                "available": mod_info.available,
                "version_id": mod_info.version_id,
                "loader_types": list(mod_info.loader_types) if mod_info.loader_types else None,
                "download_url": mod_info.download_url,
                "filename": mod_info.filename,
                "error": mod_info.error,
            },
        )

        return mod_info

    except requests.exceptions.RequestException as e:
        return ModInfo(
            name=slug,
            slug=slug,
            url=f"https://modrinth.com/mod/{slug}",
            versions=[],
            available=False,
            error=str(e),
        )


def get_mod_dependencies(version_id: str) -> List[Dict[str, str]]:
    cached_data = cache.get_cached_data("deps", version_id, "all")
    if cached_data:
        return cached_data

    try:
        url = f"https://api.modrinth.com/v2/version/{version_id}"
        response = cache.make_request(url)
        response.raise_for_status()
        version_data = response.json()

        dependencies: List[Dict[str, str]] = []
        if "dependencies" in version_data:
            dependencies = [
                dep for dep in version_data["dependencies"] if dep["dependency_type"] == "required"
            ]

        cache.cache_data("deps", version_id, "all", dependencies)
        return dependencies
    except requests.exceptions.RequestException:
        return []


def get_mod_name(mod_id: str) -> Optional[str]:
    cached_data = cache.get_cached_data("names", mod_id, "all")
    if cached_data:
        return cached_data.get("title")

    try:
        url = f"https://api.modrinth.com/v2/project/{mod_id}"
        response = cache.make_request(url)
        response.raise_for_status()
        project_data = response.json()

        cache.cache_data("names", mod_id, "all", project_data)
        return project_data["title"]
    except requests.exceptions.RequestException:
        return None
