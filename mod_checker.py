import requests
import re
import json
import os
import argparse
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass
from datetime import datetime
from packaging import version
import sys
from rich.console import Console
from rich.table import Table, box
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich import print as rprint
from pathlib import Path
import time

console = Console()

# Cache configuration
CACHE_DIR = Path("modrinth_cache")
CACHE_DURATION = 3600  # 1 hour in seconds

class ModrinthCache:
    def __init__(self):
        self.cache_dir = CACHE_DIR
        self.cache_dir.mkdir(exist_ok=True)
        self.rate_limit = 300
        self.rate_remaining = 300
        self.rate_reset = 0
        self.last_request_time = 0
        self.min_request_interval = 0.1  # Minimum time between requests in seconds

    def get_all_data(self, mod_slug: str) -> Optional[dict]:
        """Return cached project and version list if available."""
        cache_file = self._get_mod_cache_file(mod_slug)
        if cache_file.exists():
            try:
                cache_data = json.loads(cache_file.read_text())
                key = f"{mod_slug}_all"
                if key in cache_data:
                    entry = cache_data[key]
                    if time.time() - entry["cached_at"] < CACHE_DURATION:
                        return entry["data"]
            except (json.JSONDecodeError, KeyError):
                pass
        return None

    def cache_all_data(self, mod_slug: str, data: dict) -> None:
        """Cache project info and all versions."""
        cache_file = self._get_mod_cache_file(mod_slug)
        if cache_file.exists():
            try:
                cache_data = json.loads(cache_file.read_text())
            except json.JSONDecodeError:
                cache_data = {}
        else:
            cache_data = {}

        cache_data[f"{mod_slug}_all"] = {
            "cached_at": time.time(),
            "data": data,
        }
        cache_file.write_text(json.dumps(cache_data, indent=2))

    def update_rate_limits(self, headers: Dict[str, str]) -> None:
        """Update rate limit information from response headers."""
        self.rate_limit = int(headers.get('X-Ratelimit-Limit', 300))
        self.rate_remaining = int(headers.get('X-Ratelimit-Remaining', 300))
        self.rate_reset = int(headers.get('X-Ratelimit-Reset', 0))

    def should_wait(self) -> float:
        """Return the number of seconds to wait before next request."""
        if self.rate_remaining < 10:
            return max(0, self.rate_reset)
        
        time_since_last = time.time() - self.last_request_time
        if time_since_last < self.min_request_interval:
            return self.min_request_interval - time_since_last
        return 0

    def _get_mod_cache_file(self, mod_slug: str) -> Path:
        """Get the cache file path for a mod."""
        return self.cache_dir / f"{mod_slug}.json"

    def get_cached_data(self, mod_slug: str, version: str, loader: str) -> Optional[dict]:
        """Get cached mod data if it exists and is not expired."""
        cache_file = self._get_mod_cache_file(mod_slug)
        if cache_file.exists():
            try:
                cache_data = json.loads(cache_file.read_text())
                version_key = f"{version}_{loader}"
                if version_key in cache_data:
                    data = cache_data[version_key]
                    if time.time() - data['cached_at'] < CACHE_DURATION:
                        return data['data']
            except (json.JSONDecodeError, KeyError):
                pass
        return None

    def cache_data(self, mod_slug: str, version: str, loader: str, data: dict) -> None:
        """Cache mod data with timestamp."""
        cache_file = self._get_mod_cache_file(mod_slug)
        version_key = f"{version}_{loader}"
        
        # Load existing cache or create new
        if cache_file.exists():
            try:
                cache_data = json.loads(cache_file.read_text())
            except json.JSONDecodeError:
                cache_data = {}
        else:
            cache_data = {}
        
        # Update cache with new data
        cache_data[version_key] = {
            'cached_at': time.time(),
            'data': data
        }
        
        # Write updated cache
        cache_file.write_text(json.dumps(cache_data, indent=2))

    def make_request(self, url: str) -> requests.Response:
        """Make a rate-limited request."""
        wait_time = self.should_wait()
        if wait_time > 0:
            time.sleep(wait_time)

        response = requests.get(url)
        self.last_request_time = time.time()
        self.update_rate_limits(response.headers)
        return response

@dataclass
class VersionCheckResult:
    version: str
    compatible: bool
    incompatible_mods: List[Tuple[str, List[str]]]  # List of (mod_name, available_versions)

@dataclass
class ModInfo:
    name: str
    slug: str
    url: str
    versions: List[str]
    available: bool
    version_id: Optional[str] = None
    loader_types: Set[str] = None
    download_url: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None

def parse_minecraft_version(ver: str) -> version.Version:
    """Parse a Minecraft version string into a comparable version object."""
    try:
        return version.parse(ver)
    except version.InvalidVersion:
        # Handle special cases like snapshots
        return version.parse("0.0.0")

def sort_minecraft_versions(versions: List[str]) -> List[str]:
    """Sort Minecraft versions in descending order."""
    return sorted(versions, key=parse_minecraft_version, reverse=True)

def check_version_compatibility(mods_info: List[ModInfo], test_version: str, loader_type: str) -> VersionCheckResult:
    """Check compatibility of all mods for a specific version."""
    incompatible_mods = []
    
    for mod in mods_info:
        result = check_mod_version(mod.slug, test_version, loader_type)
        if not result.available:
            incompatible_mods.append((mod.name, result.versions))
    
    return VersionCheckResult(
        version=test_version,
        compatible=len(incompatible_mods) == 0,
        incompatible_mods=incompatible_mods
    )

def find_next_compatible_version(mods_info: List[ModInfo], current_version: str, 
                               loader_type: str, allow_downgrade: bool = False) -> Tuple[Optional[str], List[VersionCheckResult]]:
    """Find the next Minecraft version where all mods are compatible."""
    # Get all available versions for each mod
    all_versions = set()
    for mod in mods_info:
        all_versions.update(mod.versions)
    
    # Sort versions in descending order
    sorted_versions = sort_minecraft_versions(list(all_versions))
    current_ver = parse_minecraft_version(current_version)
    
    # Filter versions based on downgrade preference
    if not allow_downgrade:
        sorted_versions = [v for v in sorted_versions if parse_minecraft_version(v) >= current_ver]
    
    version_checks = []
    # Try each version
    for test_version in sorted_versions:
        if test_version == current_version:
            continue
            
        check_result = check_version_compatibility(mods_info, test_version, loader_type)
        version_checks.append(check_result)
        
        if check_result.compatible:
            return test_version, version_checks
                
    return None, version_checks

def extract_modrinth_links(input_file: str) -> List[Dict[str, str]]:
    """Extract Modrinth mod URLs from the input file.
    
    Supports:
    - Full Modrinth URLs (https://modrinth.com/mod/some-mod)
    - Markdown links to Modrinth
    """
    mods = []
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Find markdown links that contain modrinth.com
    md_pattern = r'\[([^\]]+)\]\((https://modrinth\.com/mod/[^)]+)\)'
    md_matches = re.finditer(md_pattern, content)
    
    for match in md_matches:
        name = match.group(1)
        url = match.group(2)
        slug = url.split('/')[-1].split(')')[0]  # Handle cases where URL might have trailing characters
        mods.append({
            'name': name,
            'url': url,
            'slug': slug
        })
    
    # Find plain URLs that contain modrinth.com
    url_pattern = r'https://modrinth\.com/mod/([^/\s)]+)'
    url_matches = re.finditer(url_pattern, content)
    
    for match in url_matches:
        slug = match.group(1)
        # Skip if we already found this mod in a markdown link
        if not any(mod['slug'] == slug for mod in mods):
            mods.append({
                'name': slug,  # Will be updated later with actual name
                'url': f'https://modrinth.com/mod/{slug}',
                'slug': slug
            })
    
    if not mods:
        console.print("[yellow]Warning: No Modrinth mod links found in the input file.[/]")
        console.print("[yellow]Make sure your file contains either:")
        console.print("[yellow]  - Markdown links: [Mod Name](https://modrinth.com/mod/mod-slug)")
        console.print("[yellow]  - Direct URLs: https://modrinth.com/mod/mod-slug")
    
    return mods

def check_mod_version(slug: str, target_version: str, loader_type: str) -> ModInfo:
    """Check if a mod is available for the specified Minecraft version and loader type."""
    cache = ModrinthCache()
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
            name=project_data['title'],
            slug=slug,
            url=f"https://modrinth.com/mod/{slug}",
            versions=[],
            available=False
        )
        
        compatible_version = None
        for ver in versions:
            if loader_type in ver['loaders'] and target_version in ver['game_versions']:
                compatible_version = ver
                break
            mod_info.versions.extend(ver['game_versions'])
            mod_info.loader_types = mod_info.loader_types or set()
            mod_info.loader_types.update(ver['loaders'])
        
        if compatible_version:
            mod_info.available = True
            mod_info.version_id = compatible_version['id']
            mod_info.download_url = compatible_version['files'][0]['url']
            mod_info.filename = compatible_version['files'][0]['filename']
        
        # Remove duplicates and sort versions
        mod_info.versions = list(set(mod_info.versions))
        mod_info.versions.sort(key=lambda x: parse_minecraft_version(x), reverse=True)
        
        cache.cache_data(slug, target_version, loader_type, {
            'name': mod_info.name,
            'slug': mod_info.slug,
            'url': mod_info.url,
            'versions': mod_info.versions,
            'available': mod_info.available,
            'version_id': mod_info.version_id,
            'loader_types': list(mod_info.loader_types) if mod_info.loader_types else None,
            'download_url': mod_info.download_url,
            'filename': mod_info.filename,
            'error': mod_info.error
        })
        
        return mod_info

    except requests.exceptions.RequestException as e:
        return ModInfo(
            name=slug,
            slug=slug,
            url=f"https://modrinth.com/mod/{slug}",
            versions=[],
            available=False,
            error=str(e)
        )

def download_mod(mod_info: ModInfo, output_dir: str, progress: Optional[Progress] = None) -> bool:
    """Download a mod to the specified directory."""
    if not mod_info.available or not mod_info.download_url or not mod_info.filename:
        return False
    
    output_path = Path(output_dir) / mod_info.filename
    
    # Check if mod is already downloaded
    if output_path.exists():
        # TODO: Add hash verification here if needed
        console.print(f"[dim]Mod {mod_info.name} already exists in {output_dir}[/]")
        return True
    
    try:
        response = requests.get(mod_info.download_url, stream=True)
        response.raise_for_status()
        
        # Create output directory if it doesn't exist
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Download with progress bar
        total_size = int(response.headers.get('content-length', 0))
        
        # If we have a parent progress bar, use it
        if progress:
            task = progress.add_task(f"Downloading {mod_info.name}...", total=total_size)
            with open(output_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        progress.update(task, advance=len(chunk))
        else:
            # Create our own progress bar
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
                transient=True
            ) as progress:
                task = progress.add_task(f"Downloading {mod_info.name}...", total=total_size)
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            progress.update(task, advance=len(chunk))
        
        return True
        
    except requests.exceptions.RequestException as e:
        console.print(f"[red]Error downloading {mod_info.name}: {str(e)}[/]")
        return False

def prompt_user(question: str) -> bool:
    """Prompt the user for yes/no input."""
    console.print(f"\n{question} (yes/no): ", end="")
    try:
        response = input().lower().strip()
        while response not in ['yes', 'y', 'no', 'n']:
            console.print("Please answer 'yes' or 'no': ", end="")
            response = input().lower().strip()
        return response in ['yes', 'y']
    except (EOFError, KeyboardInterrupt):
        return False

def get_mod_dependencies(version_id: str) -> List[Dict[str, str]]:
    """Get dependencies for a specific mod version."""
    cache = ModrinthCache()
    
    # For dependencies, we'll use a special cache key format
    cached_data = cache.get_cached_data("deps", version_id, "all")
    if cached_data:
        return cached_data
    
    try:
        url = f"https://api.modrinth.com/v2/version/{version_id}"
        response = cache.make_request(url)
        response.raise_for_status()
        version_data = response.json()
        
        dependencies = []
        if 'dependencies' in version_data:
            dependencies = [
                dep for dep in version_data['dependencies']
                if dep['dependency_type'] == 'required'
            ]
        
        # Cache the dependencies
        cache.cache_data("deps", version_id, "all", dependencies)
        return dependencies
        
    except requests.exceptions.RequestException:
        return []

def get_mod_name(mod_id: str) -> Optional[str]:
    """Get the mod name from its ID using Modrinth API."""
    cache = ModrinthCache()
    
    # For mod names, we'll use a special cache key format
    cached_data = cache.get_cached_data("names", mod_id, "all")
    if cached_data:
        return cached_data.get('title')
    
    try:
        url = f"https://api.modrinth.com/v2/project/{mod_id}"
        response = cache.make_request(url)
        response.raise_for_status()
        project_data = response.json()
        
        # Cache the project data
        cache.cache_data("names", mod_id, "all", project_data)
        return project_data['title']
        
    except requests.exceptions.RequestException:
        return None

def process_dependencies(mod_info: ModInfo, version: str, loader: str, 
                       processed_mods: Set[str], output_dir: str,
                       parent_progress: Optional[Progress] = None) -> List[ModInfo]:
    """Process and download dependencies for a mod."""
    if not mod_info.version_id or not mod_info.available:
        return []
    
    dependency_results = []
    dependencies = get_mod_dependencies(mod_info.version_id)
    
    if dependencies:
        console.print(f"\n[yellow]Processing dependencies for {mod_info.name}[/]:")
        
    for dep in dependencies:
        dep_id = dep.get('project_id')
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
            
            # Recursively process nested dependencies
            nested_deps = process_dependencies(dep_result, version, loader, processed_mods, output_dir, parent_progress)
            dependency_results.extend(nested_deps)
    
    return dependency_results

def generate_compatibility_report(original_version: str, final_version: str, 
                               original_loader: str, final_loader: str,
                               results: List[ModInfo], dependencies: List[ModInfo],
                               version_checks: Optional[List[VersionCheckResult]] = None) -> str:
    """Generate a detailed compatibility report."""
    report = []
    now = datetime.now()
    
    # Header
    report.append("# Mod Compatibility Report")
    report.append(f"Generated on: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    
    # Version and Loader Information
    report.append("## Configuration Changes")
    report.append(f"- Original Minecraft Version: {original_version}")
    if original_version != final_version:
        report.append(f"- Final Minecraft Version: {final_version} (changed due to compatibility)")
    
    report.append(f"- Original Mod Loader: {original_loader}")
    if original_loader != final_loader:
        report.append(f"- Final Mod Loader: {final_loader} (changed due to compatibility)")
    report.append("")
    
    # Version Check History (if version was changed)
    if version_checks and original_version != final_version:
        report.append("## Version Check History")
        report.append("The following versions were checked before finding compatibility:")
        report.append("")
        for check in version_checks:
            if check.version == final_version:
                break
            report.append(f"### Minecraft {check.version}")
            if check.incompatible_mods:
                report.append("Incompatible mods:")
                for mod_name, versions in check.incompatible_mods:
                    report.append(f"- {mod_name}")
                    sorted_versions = sort_minecraft_versions(versions)
                    report.append(f"  - Available versions: {', '.join(sorted_versions[:5])}...")
            else:
                report.append("All mods compatible!")
            report.append("")
    
    # Compatible Mods
    compatible_mods = [mod for mod in results if mod.available]
    if compatible_mods:
        report.append("## Compatible Mods")
        for mod in compatible_mods:
            report.append(f"- [{mod.name}]({mod.url})")
            if mod.filename:  # If the mod was downloaded
                report.append(f"  - File: {mod.filename}")
        report.append("")
    
    # Required Dependencies
    if dependencies:
        report.append("## Required Dependencies")
        available_deps = [dep for dep in dependencies if dep.available]
        unavailable_deps = [dep for dep in dependencies if not dep.available]
        
        if available_deps:
            report.append("### Successfully Downloaded Dependencies:")
            for dep in available_deps:
                report.append(f"- [{dep.name}]({dep.url})")
                if dep.filename:
                    report.append(f"  - File: {dep.filename}")
        
        if unavailable_deps:
            report.append("\n### Unavailable Dependencies:")
            for dep in unavailable_deps:
                report.append(f"- [{dep.name}]({dep.url})")
                if dep.error:
                    report.append(f"  - Error: {dep.error}")
        report.append("")
    
    # Incompatible Mods
    incompatible_mods = [mod for mod in results if not mod.available]
    if incompatible_mods:
        report.append("## Incompatible Mods")
        for mod in incompatible_mods:
            report.append(f"- [{mod.name}]({mod.url})")
            if mod.error:
                report.append(f"  - Error: {mod.error}")
            elif mod.versions:
                sorted_versions = sort_minecraft_versions(mod.versions)
                report.append(f"  - Available versions: {', '.join(sorted_versions[:5])}...")
                if mod.loader_types:
                    report.append(f"  - Supported loaders: {', '.join(sorted(mod.loader_types))}")
        report.append("")
    
    return "\n".join(report)

def check_alternative_loaders(mods: List[Dict[str, str]], version: str, current_loader: str) -> Dict[str, List[ModInfo]]:
    """Check if other loaders might be more compatible."""
    all_loaders = {'fabric', 'forge', 'quilt', 'neoforge'} - {current_loader}
    loader_results = {}
    
    for loader in all_loaders:
        results = []
        for mod in mods:
            result = check_mod_version(mod['slug'], version, loader)
            results.append(result)
        
        # Only include loader if all mods are compatible
        if all(mod.available for mod in results):
            loader_results[loader] = results
    
    return loader_results

def find_common_version(mods: List[ModInfo]) -> Optional[str]:
    """Find the oldest version that works for all mods."""
    if not mods:
        return None
        
    # Get all versions for each mod
    mod_versions = [set(mod.versions) for mod in mods if mod.versions]
    if not mod_versions:
        return None
        
    # Find versions that work for all mods
    common_versions = set.intersection(*mod_versions)
    if not common_versions:
        return None
        
    # Sort versions and return the oldest one that's not a snapshot
    sorted_versions = sort_minecraft_versions([v for v in common_versions if not 'w' in v and not 'snapshot' in v])
    return sorted_versions[0] if sorted_versions else None

def check_loader_compatibility(mods: List[Dict[str, str]], version: str, loader: str) -> Tuple[List[ModInfo], int]:
    """Check how many mods are compatible with a specific loader and version."""
    results = []
    compatible_count = 0
    for mod in mods:
        result = check_mod_version(mod['slug'], version, loader)
        results.append(result)
        if result.available:
            compatible_count += 1
    return results, compatible_count

def find_best_loader(mods: List[Dict[str, str]], version: str, current_loader: str, 
                    preferred_loader: Optional[str] = None) -> Tuple[str, List[ModInfo], Dict[str, int]]:
    """Find the loader that supports the most mods for a given version."""
    all_loaders = {'fabric', 'forge', 'neoforge', 'quilt'}
    loader_stats = {}  # Store compatibility stats for each loader
    best_loader = current_loader
    best_count = 0
    best_results = []
    
    # Check each loader
    for loader in all_loaders:
        results, compatible_count = check_loader_compatibility(mods, version, loader)
        loader_stats[loader] = compatible_count
        
        # Update best loader based on compatibility count and preferences
        is_better = False
        if compatible_count > best_count:
            is_better = True
        elif compatible_count == best_count:
            # If counts are equal, prefer the current loader
            if loader == current_loader:
                is_better = True
            # Then prefer the preferred loader
            elif preferred_loader and loader == preferred_loader:
                is_better = True
        
        if is_better:
            best_count = compatible_count
            best_loader = loader
            best_results = results
    
    return best_loader, best_results, loader_stats

def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="""
Minecraft Mod Compatibility Checker

Checks compatibility between Minecraft mods from Modrinth, manages dependencies,
and can automatically download compatible versions.

Example usage:
  python mod_checker.py --version 1.20.4 --loader fabric --download
  python mod_checker.py --version 1.20.4 --loader fabric --input my_mods.txt --output-dir custom_mods
""",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--version', required=True,
                      help='Minecraft version to check compatibility with (e.g., "1.20.4")')
    parser.add_argument('--loader', required=True, choices=['fabric', 'forge', 'quilt', 'neoforge'],
                      help='Mod loader type (fabric, forge, quilt, or neoforge)')
    parser.add_argument('--preferred-alt-loader', choices=['fabric', 'forge', 'quilt', 'neoforge'],
                      help='Preferred alternative loader if current loader is incompatible')
    parser.add_argument('--input', default='TheGreatSpaceProject.md',
                      help='Input file containing mod IDs or URLs (default: TheGreatSpaceProject.md)')
    parser.add_argument('--output-dir', default='mods',
                      help='Directory to save downloaded mods (default: mods)')
    parser.add_argument('--download', action='store_true',
                      help='Download mods if they are compatible')
    parser.add_argument('--allow-downgrade', action='store_true',
                      help='Allow checking older versions if current version is incompatible')
    parser.add_argument('--auto-accept', action='store_true',
                      help='Automatically accept version and loader changes')

    return parser.parse_args()

def main():
    args = parse_args()
    original_version = args.version  # Store original version for reporting
    original_loader = args.loader    # Store original loader for reporting
    
    # Normalize output directory path
    args.output_dir = str(Path(args.output_dir))
    
    console.print(Panel.fit(
        f"[blue]{args.input}[/]\n"
        f"Checking mods for Minecraft {args.version} using {args.loader}",
        title="[bold green]Minecraft Mod Checker[/]"
    ))
    
    if args.preferred_alt_loader:
        console.print(f"[dim]Preferred alternative loader: {args.preferred_alt_loader}[/]")
    
    processed_mods = set()
    mods = extract_modrinth_links(args.input)
    version_checks = []
    
    if not mods:
        return
    
    # Initial compatibility check
    results = []
    for mod in mods:
        result = check_mod_version(mod['slug'], args.version, args.loader)
        results.append(result)
    
    # Check if any mods are incompatible
    incompatible_mods = [mod for mod in results if not mod.available]
    
    if incompatible_mods:
        console.print(f"\nSome mods are not compatible with Minecraft {args.version} using {args.loader}:")
        for mod in incompatible_mods:
            console.print(f"- [red]{mod.name}[/]")
            if mod.versions:
                console.print(f"  Available versions: [cyan]{', '.join(sort_minecraft_versions(mod.versions)[:5])}...")
        
        # Try to find a common version that works for all mods
        common_version = find_common_version(results)
        if common_version:
            console.print(f"\n[green]Found a version compatible with all mods: {common_version}[/]")
            
            # Check which loader is best for this version
            best_loader, best_results, loader_stats = find_best_loader(
                mods, common_version, args.loader, args.preferred_alt_loader
            )
            current_compatible = loader_stats[args.loader]
            best_compatible = loader_stats[best_loader]
            
            # Show compatibility stats for all loaders
            console.print(f"\n[yellow]Loader compatibility for version {common_version}:[/]")
            for loader, compatible_count in loader_stats.items():
                prefix = "*" if loader == best_loader else " "
                status = "[green]" if compatible_count == len(mods) else "[yellow]"
                console.print(f"{prefix} {loader}: {status}{compatible_count}/{len(mods)} mods compatible[/]")
            
            # If another loader supports more mods, suggest switching
            if best_loader != args.loader and best_compatible > current_compatible:
                if args.auto_accept:
                    args.loader = best_loader
                    args.version = common_version
                    results = best_results
                    console.print(f"\n[yellow]Auto-accepted version change to: {common_version}[/]")
                    console.print(f"[yellow]Auto-accepted loader change to: {best_loader}[/]")
                else:
                    if prompt_user(f"Would you like to switch to {best_loader}?"):
                        args.loader = best_loader
                        args.version = common_version
                        results = best_results
                    elif prompt_user(f"Would you like to use version {common_version} with {args.loader}?"):
                        args.version = common_version
                        results = []
                        for mod in mods:
                            result = check_mod_version(mod['slug'], args.version, args.loader)
                            results.append(result)
            else:
                # Just update the version if needed
                if args.auto_accept:
                    args.version = common_version
                    console.print(f"[yellow]Auto-accepted version change to: {common_version}[/]")
                elif prompt_user(f"Would you like to use version {common_version}?"):
                    args.version = common_version
                
                # Update results with new version
                results = []
                for mod in mods:
                    result = check_mod_version(mod['slug'], args.version, args.loader)
                    results.append(result)
        else:
            # If no common version, try finding a compatible version with current loader
            next_version, version_checks = find_next_compatible_version(results, args.version, args.loader, args.allow_downgrade)
            
            if not next_version:
                # If no compatible version found, check other loaders
                console.print("\n[yellow]Checking alternative mod loaders...[/]")
                alternative_loaders = check_alternative_loaders(mods, args.version, args.loader)
                
                if alternative_loaders:
                    console.print("\n[green]Found compatible loader(s):[/]")
                    for loader, loader_results in alternative_loaders.items():
                        console.print(f"- [cyan]{loader}[/] supports all mods at version {args.version}")
                    
                    if args.download:
                        loader_options = list(alternative_loaders.keys())
                        if args.auto_accept and loader_options:
                            args.loader = loader_options[0]
                            results = alternative_loaders[args.loader]
                            console.print(f"\n[yellow]Auto-selected loader: {args.loader}[/]")
                        else:
                            loader_list = ", ".join(f"'{l}'" for l in loader_options[:-1]) + f" or '{loader_options[-1]}'"
                            console.print(f"\nWould you like to switch to {loader_list}?")
                            for loader in loader_options:
                                if prompt_user(f"Use {loader}?"):
                                    args.loader = loader
                                    results = alternative_loaders[loader]
                                    break
                            else:
                                console.print("[yellow]No alternative loader selected. Keeping original choice.[/]")
                else:
                    console.print("[red]No compatible loaders found for this version.[/]")
                    if common_version:
                        console.print(f"\n[yellow]Consider using version {common_version} which is compatible with all mods.[/]")
    
    # Print results
    console.print(f"\nResults for Minecraft {args.version} ({args.loader}):")
    
    # Create a table for results
    table = Table(box=box.ROUNDED)
    table.add_column("Status", justify="center")
    table.add_column("Mod", style="bold")
    table.add_column("Details", style="dim")
    
    # Process mods with a progress bar for downloads
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True
    ) as progress:
        for mod in results:
            status = "[green]+[/]" if mod.available else "[red]-[/]"
            details = []
            
            if mod.available:
                if args.download:
                    if download_mod(mod, args.output_dir, progress):
                        details.append(f"Downloaded to {args.output_dir}/{mod.filename}")
            else:
                details.append("Not available")
                if mod.versions:
                    sorted_versions = sort_minecraft_versions(mod.versions)
                    details.append(f"Available versions: {', '.join(sorted_versions[:3])}...")
                if mod.loader_types:
                    details.append(f"Supported loaders: {', '.join(mod.loader_types)}")
            
            table.add_row(
                status,
                mod.name,
                "\n".join(details)
            )
    
    console.print(table)
    
    # Process dependencies if downloading
    if args.download:
        console.print("\nChecking for required dependencies...")
        dependencies = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            transient=True
        ) as progress:
            for mod in results:
                if mod.available:
                    deps = process_dependencies(mod, args.version, args.loader, processed_mods, args.output_dir, progress)
                    dependencies.extend(deps)
        
        if dependencies:
            console.print("\n\nDependency Summary:")
            dep_table = Table(box=box.ROUNDED)
            dep_table.add_column("Status", justify="center")
            dep_table.add_column("Dependency", style="bold")
            
            for dep in dependencies:
                status = "[green]+[/]" if dep.available else "[red]-[/]"
                dep_table.add_row(status, f"{dep.name} (dependency)")
            
            console.print(dep_table)
    
    # Generate and save report
    report_content = generate_compatibility_report(
        original_version=original_version,
        final_version=args.version,
        original_loader=original_loader,
        final_loader=args.loader,
        results=results,
        dependencies=dependencies if args.download else [],
        version_checks=version_checks
    )
    
    report_file = 'mod_compatibility_report.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_content)
    
    console.print(f"\n[dim]Detailed report saved to {report_file}[/]")

if __name__ == "__main__":
    main()
