from datetime import datetime
from typing import List

from .models import ModInfo, VersionCheckResult


def generate_compatibility_report(
    original_version: str,
    final_version: str,
    original_loader: str,
    final_loader: str,
    results: List[ModInfo],
    dependencies: List[ModInfo],
    version_checks: List[VersionCheckResult] | None = None,
) -> str:
    report: List[str] = []
    now = datetime.now()

    report.append("# Mod Compatibility Report")
    report.append(f"Generated on: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")

    report.append("## Configuration Changes")
    report.append(f"- Original Minecraft Version: {original_version}")
    if original_version != final_version:
        report.append(f"- Final Minecraft Version: {final_version} (changed due to compatibility)")
    report.append(f"- Original Mod Loader: {original_loader}")
    if original_loader != final_loader:
        report.append(f"- Final Mod Loader: {final_loader} (changed due to compatibility)")
    report.append("")

    report.append("## Compatible Mods")
    for mod in results:
        status = "Available" if mod.available else "Not available"
        line = f"- {mod.name}: {status}"
        if mod.available and mod.filename:
            line += f" ({mod.filename})"
        report.append(line)
    report.append("")

    if dependencies:
        report.append("## Dependencies")
        for dep in dependencies:
            report.append(f"- {dep.name}")
        report.append("")

    if version_checks:
        report.append("## Version Compatibility Checks")
        for vc in version_checks:
            comp = "compatible" if vc.compatible else "incompatible"
            report.append(f"- {vc.version}: {comp}")
            if vc.incompatible_mods:
                for mod, avail in vc.incompatible_mods:
                    report.append(f"  - {mod}: {', '.join(avail[:5])}")
        report.append("")

    return "\n".join(report)
