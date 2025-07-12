import re
from pathlib import Path
from typing import Dict, List

from packaging import version
from rich.console import Console

console = Console()


def parse_minecraft_version(ver: str) -> version.Version:
    try:
        return version.parse(ver)
    except version.InvalidVersion:
        return version.parse("0.0.0")


def sort_minecraft_versions(versions: List[str]) -> List[str]:
    return sorted(versions, key=parse_minecraft_version, reverse=True)


def extract_modrinth_links(input_file: str) -> List[Dict[str, str]]:
    mods: List[Dict[str, str]] = []
    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read()

    md_pattern = r"\[([^\]]+)\]\((https://modrinth\.com/mod/[^)]+)\)"
    for match in re.finditer(md_pattern, content):
        name = match.group(1)
        url = match.group(2)
        slug = url.split("/")[-1].split(")")[0]
        mods.append({"name": name, "url": url, "slug": slug})

    url_pattern = r"https://modrinth\.com/mod/([^/\s)]+)"
    for match in re.finditer(url_pattern, content):
        slug = match.group(1)
        if not any(mod["slug"] == slug for mod in mods):
            mods.append({"name": slug, "url": f"https://modrinth.com/mod/{slug}", "slug": slug})

    if not mods:
        console.print("[yellow]Warning: No Modrinth mod links found in the input file.[/]")
        console.print("[yellow]Make sure your file contains either:")
        console.print("[yellow]  - Markdown links: [Mod Name](https://modrinth.com/mod/mod-slug)")
        console.print("[yellow]  - Direct URLs: https://modrinth.com/mod/mod-slug")

    return mods


def prompt_user(question: str) -> bool:
    console.print(f"\n{question} (yes/no): ", end="")
    try:
        response = input().lower().strip()
        while response not in ["yes", "y", "no", "n"]:
            console.print("Please answer 'yes' or 'no': ", end="")
            response = input().lower().strip()
        return response in ["yes", "y"]
    except (EOFError, KeyboardInterrupt):
        return False
