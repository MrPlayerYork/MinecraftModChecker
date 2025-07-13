# Minecraft Mod Checker

A Python script to check compatibility and download Minecraft mods from Modrinth.

## Features

- Validates mod compatibility for specified Minecraft version and mod loader
- Automatically finds compatible versions if initial version check fails
- Checks alternative mod loaders (fabric, forge, quilt, neoforge) if needed
- Downloads mods and their required dependencies
- Generates detailed compatibility reports
- Supports both direct Modrinth URLs and markdown-style links

## Requirements

- Python 3.7 or higher
- Required packages (install via `pip install -r requirements.txt`):
  - requests
  - rich

## Usage

```bash
python mod_checker.py --input <input_file> --version <minecraft_version> --loader <mod_loader> [options]
```

### Arguments

- `--input`: Path to file containing mod links (required)
- `--version`: Minecraft version to check against (required)
- `--loader`: Mod loader to use (fabric, forge, quilt, or neoforge) (required)
- `--output-dir`: Directory to save downloaded mods (default: mods)
- `--download`: Download compatible mods (optional)
- `--allow-downgrade`: Allow checking older versions if needed (optional)

### Input File Format

The input file should contain Modrinth mod links in one of these formats:

```markdown
- [Mod Name](https://modrinth.com/mod/mod-slug)
- https://modrinth.com/mod/another-mod
```

Only full Modrinth URLs are supported. Mod slugs or IDs alone are not accepted.

## Output

The script provides:

1. Real-time console output showing:
   - Compatibility check results
   - Version change suggestions if needed
   - Alternative loader suggestions
   - Download progress
   - Dependency processing

2. A detailed markdown report (`mod_compatibility_report.md`) containing:
   - Version information (original and final)
   - Version check history
   - List of compatible mods
   - Required dependencies
   - Incompatible mods with available versions

## Examples

Check mod compatibility:
```bash
python mod_checker.py --input mods.md --version 1.20.1 --loader fabric
```

Check and download mods:
```bash
python mod_checker.py --input mods.md --version 1.20.1 --loader fabric --download
```

Allow version downgrades:
```bash
python mod_checker.py --input mods.md --version 1.20.1 --loader fabric --download --allow-downgrade
```

## Error Handling

The script provides clear error messages for common issues:
- Invalid mod URLs
- Incompatible versions
- Missing dependencies
- Download failures

If the initial version/loader combination isn't compatible, the script will:
1. Try to find a compatible version with the current loader
2. If that fails, check if other loaders support all mods
3. Provide suggestions for version or loader changes

## Notes

- The script prioritizes finding a compatible version with your chosen loader before suggesting alternative loaders
- The compatibility report provides a complete record of the process and results
- Downloaded mods and dependencies are saved in the specified output directory

- Recent changes have increased the speed and efficientcy of the script, however, there is a lot of type issues in the code. While this doesn't seem to effect the overall function, some features aren't working and I'd like to make the typing better anyway. Thus, a rewrite is planned and more commits will be coming in the future.

## License (Short)
<a href="https://github.com/MrPlayerYork/MinecraftModChecker">MinecraftModChecker</a> © 2025 by <a href="https://github.com/MrPlayerYork">MrPlayerYork</a> is licensed under <a href="https://creativecommons.org/licenses/by-nc-sa/4.0/">CC BY-NC-SA 4.0</a>

<img src="https://mirrors.creativecommons.org/presskit/icons/cc.svg" alt="" style="max-width: 1em;max-height:1em;margin-left: .2em;"><img src="https://mirrors.creativecommons.org/presskit/icons/by.svg" alt="" style="max-width: 1em;max-height:1em;margin-left: .2em;"><img src="https://mirrors.creativecommons.org/presskit/icons/nc.svg" alt="" style="max-width: 1em;max-height:1em;margin-left: .2em;"><img src="https://mirrors.creativecommons.org/presskit/icons/sa.svg" alt="" style="max-width: 1em;max-height:1em;margin-left: .2em;">
