from pathlib import Path
from typing import List, Optional, Set

import requests
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

from .models import ModInfo
from .modrinth_api import check_mod_version, get_mod_dependencies, get_mod_name
from .utils import console


def download_mod(mod_info: ModInfo, output_dir: str, progress: Optional[Progress] = None) -> bool:
    if not mod_info.available or not mod_info.download_url or not mod_info.filename:
        return False

    output_path = Path(output_dir) / mod_info.filename
    if output_path.exists():
        console.print(f"[dim]Mod {mod_info.name} already exists in {output_dir}[/]")
        return True

    try:
        response = requests.get(mod_info.download_url, stream=True)
        response.raise_for_status()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        total_size = int(response.headers.get("content-length", 0))

        if progress:
            task = progress.add_task(f"Downloading {mod_info.name}...", total=total_size)
            with open(output_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))
        else:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
                transient=True,
            ) as p:
                task = p.add_task(f"Downloading {mod_info.name}...", total=total_size)
                with open(output_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            p.update(task, advance=len(chunk))
        return True
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Error downloading {mod_info.name}: {str(e)}[/]")
        return False


def process_dependencies(
    mod_info: ModInfo,
    version: str,
    loader: str,
    processed_mods: Set[str],
    output_dir: str,
    parent_progress: Optional[Progress] = None,
) -> List[ModInfo]:
    if not mod_info.version_id or not mod_info.available:
        return []

    dependency_results: List[ModInfo] = []
    dependencies = get_mod_dependencies(mod_info.version_id)

    if dependencies:
        console.print(f"\n[yellow]Processing dependencies for {mod_info.name}[/]:")

    for dep in dependencies:
        dep_id = dep.get("project_id")
        if not dep_id or dep_id in processed_mods:
            continue

        processed_mods.add(dep_id)
        dep_name = get_mod_name(dep_id)
        if dep_name:
            console.print(f"  [green]+[/] Found dependency: {dep_name}")

        dep_result = check_mod_version(dep_id, version, loader)
        if dep_result.available:
            dependency_results.append(dep_result)
            if download_mod(dep_result, output_dir, parent_progress):
                console.print(f"    [dim]Downloaded to {output_dir}/{dep_result.filename}[/]")
            nested_deps = process_dependencies(dep_result, version, loader, processed_mods, output_dir, parent_progress)
            dependency_results.extend(nested_deps)

    return dependency_results
