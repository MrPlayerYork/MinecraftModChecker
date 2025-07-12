from pathlib import Path
from typing import Dict, List, Set
import argparse

from rich.panel import Panel
from rich.table import Table, box
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from modchecker import ModInfo, VersionCheckResult, find_common_version
from modchecker.cache import cache
from modchecker.utils import console, extract_modrinth_links, sort_minecraft_versions, prompt_user
from modchecker.modrinth_api import check_mod_version
from modchecker.compatibility import (
    find_next_compatible_version,
    check_loader_compatibility,
    find_best_loader,
)
from modchecker.downloader import download_mod, process_dependencies
from modchecker.report import generate_compatibility_report


def check_alternative_loaders(mods: List[Dict[str, str]], version: str, current_loader: str) -> Dict[str, List[ModInfo]]:
    all_loaders = {'fabric', 'forge', 'quilt', 'neoforge'} - {current_loader}
    loader_results: Dict[str, List[ModInfo]] = {}

    for loader in all_loaders:
        results: List[ModInfo] = []
        for mod in mods:
            result = check_mod_version(mod['slug'], version, loader)
            results.append(result)
        if all(mod.available for mod in results):
            loader_results[loader] = results

    return loader_results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="""
Minecraft Mod Compatibility Checker

Checks compatibility between Minecraft mods from Modrinth, manages dependencies, and can automatically download compatible versions.

Example usage:
  python mod_checker.py --version 1.20.4 --loader fabric --download
  python mod_checker.py --version 1.20.4 --loader fabric --input my_mods.txt --output-dir custom_mods
""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
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


def main() -> None:
    args = parse_args()
    original_version = args.version
    original_loader = args.loader

    args.output_dir = str(Path(args.output_dir))

    console.print(Panel.fit(
        f"[blue]{args.input}[/]\n",
        f"Checking mods for Minecraft {args.version} using {args.loader}",
        title="[bold green]Minecraft Mod Checker[/]",
    ))

    if args.preferred_alt_loader:
        console.print(f"[dim]Preferred alternative loader: {args.preferred_alt_loader}[/]")

    processed_mods: Set[str] = set()
    mods: List[Dict[str, str]] = extract_modrinth_links(args.input)
    version_checks: List[VersionCheckResult] = []

    if not mods:
        return

    results: List[ModInfo] = []
    for mod in mods:
        result = check_mod_version(mod['slug'], args.version, args.loader)
        results.append(result)

    incompatible_mods: List[ModInfo] = [mod for mod in results if not mod.available]

    if incompatible_mods:
        console.print(f"\nSome mods are not compatible with Minecraft {args.version} using {args.loader}:")
        for mod in incompatible_mods:
            console.print(f"- [red]{mod.name}[/]")
            if mod.versions:
                console.print(f"  Available versions: [cyan]{', '.join(sort_minecraft_versions(mod.versions)[:5])}...")

        common_version = find_common_version(results)
        if common_version:
            console.print(f"\n[green]Found a version compatible with all mods: {common_version}[/]")
            best_loader, best_results, loader_stats = find_best_loader(
                mods, common_version, args.loader, args.preferred_alt_loader
            )
            current_compatible = loader_stats[args.loader]
            best_compatible = loader_stats[best_loader]

            console.print(f"\n[yellow]Loader compatibility for version {common_version}:[/]")
            for loader, compatible_count in loader_stats.items():
                prefix = '*' if loader == best_loader else ' '
                status = '[green]' if compatible_count == len(mods) else '[yellow]'
                console.print(f"{prefix} {loader}: {status}{compatible_count}/{len(mods)} mods compatible[/]")

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
                        results = [check_mod_version(mod['slug'], args.version, args.loader) for mod in mods]
            else:
                if args.auto_accept:
                    args.version = common_version
                    console.print(f"[yellow]Auto-accepted version change to: {common_version}[/]")
                elif prompt_user(f"Would you like to use version {common_version}?"):
                    args.version = common_version

                results = [check_mod_version(mod['slug'], args.version, args.loader) for mod in mods]
        else:
            next_version, version_checks = find_next_compatible_version(results, args.version, args.loader, args.allow_downgrade)
            if not next_version:
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

    console.print(f"\nResults for Minecraft {args.version} ({args.loader}):")

    table = Table(box=box.ROUNDED)
    table.add_column("Status", justify="center")
    table.add_column("Mod", style="bold")
    table.add_column("Details", style="dim")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
        transient=True,
    ) as progress:
        for mod in results:
            status = "[green]+[/]" if mod.available else "[red]-[/]"
            details: List[str] = []
            if mod.available and args.download:
                if download_mod(mod, args.output_dir, progress):
                    details.append(f"Downloaded to {args.output_dir}/{mod.filename}")
            elif not mod.available:
                details.append("Not available")
                if mod.versions:
                    sorted_versions = sort_minecraft_versions(mod.versions)
                    details.append(f"Available versions: {', '.join(sorted_versions[:3])}...")
                if mod.loader_types:
                    details.append(f"Supported loaders: {', '.join(mod.loader_types)}")
            table.add_row(status, mod.name, "\n".join(details))

    console.print(table)

    dependencies: List[ModInfo] = []
    if args.download:
        console.print("\nChecking for required dependencies...")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
            transient=True,
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

    report_content = generate_compatibility_report(
        original_version=original_version,
        final_version=args.version,
        original_loader=original_loader,
        final_loader=args.loader,
        results=results,
        dependencies=dependencies if args.download else [],
        version_checks=version_checks,
    )

    report_file = 'mod_compatibility_report.md'
    with open(report_file, 'w', encoding='utf-8') as f:
        f.write(report_content)

    console.print(f"\n[dim]Detailed report saved to {report_file}[/]")


if __name__ == "__main__":  # pragma: no cover - CLI entry
    main()
