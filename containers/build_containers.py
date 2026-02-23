#!/usr/bin/env python3
"""
Build script for UniProf profiler containers.

This script builds multi-architecture Docker containers for various language/platform profilers
and optionally pushes them to the GitHub Container Registry.

Note: When building multi-architecture images, Docker creates separate images for each
architecture plus a manifest list. This results in multiple images in the registry:
- One tagged image (e.g., "latest") which is the manifest list
- Several untagged images (SHA hashes) for individual architectures
This is normal behavior for multi-arch builds.

Usage:
    uv run containers/build_containers.py python [--push]
"""

import argparse
import subprocess
import sys
import os
import json
import platform
from pathlib import Path
from typing import List, Optional, Dict, Tuple


SUPPORTED_PLATFORMS = ["python", "nodejs", "ruby", "php", "native", "beam", "jvm", "dotnet"]
REGISTRY = "ghcr.io/indragiek/uniprof"
ARCHITECTURES = ["linux/amd64", "linux/arm64"]


def run_command(cmd: List[str], check: bool = True, stream_output: bool = False) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    # Making a change to see if the code review bot will get triggered
    print(f"Running a command: {' '.join(cmd)}")
    if stream_output:
        # Stream output in real-time
        return subprocess.run(cmd, check=check)
    else:
        return subprocess.run(cmd, check=check, capture_output=True, text=True)


def check_docker_buildx() -> bool:
    """Check if Docker buildx is available and configured."""
    try:
        # Check if buildx is available
        result = run_command(["docker", "buildx", "version"], check=False)
        if result.returncode != 0:
            print("Error: Docker buildx is not available")
            print("Please ensure you have Docker Desktop or Docker CE with buildx plugin")
            return False

        # Check if we have a builder instance
        result = run_command(["docker", "buildx", "ls"], check=False)
        if result.returncode == 0 and "docker-container" in result.stdout:
            return True

        # Create a new builder instance with multi-arch support
        print("Creating buildx builder instance...")
        run_command(["docker", "buildx", "create", "--name", "uniprof-builder", "--use", "--platform", ",".join(ARCHITECTURES)])
        run_command(["docker", "buildx", "inspect", "--bootstrap"])

        return True
    except FileNotFoundError:
        print("Error: Docker command not found")
        return False


def get_version_info(platform: str, temp_tag: str) -> Dict[str, str]:
    """Extract version information from a built container."""
    versions = {}

    # Platform-specific commands to get version info
    # Only include tools installed in the Dockerfile, not in bootstrap script
    if platform == "python":
        commands = {
            "uv": ["uv", "--version"],
            "py-spy": ["py-spy", "--version"]
        }
    elif platform == "nodejs":
        commands = {
            "nvm": ["bash", "-c", "source /root/.nvm/nvm.sh && nvm --version"]
        }
    elif platform == "ruby":
        commands = {
            "rbspy": ["rbspy", "--version"],
            "rbenv": ["/usr/local/rbenv/bin/rbenv", "--version"]
        }
    elif platform == "php":
        commands = {
            "php": ["php", "-v"],
            "composer": ["composer", "--version"],
            "excimer": ["php", "-r", "echo phpversion('excimer');"]
        }
    elif platform == "native":
        commands = {
            "perf": ["perf", "version"],
            "binutils": ["objdump", "--version"]
        }
    elif platform == "beam":
        commands = {
            "erlang": ["erl", "-noshell", "-eval", "io:format(\"~s\", [erlang:system_info(otp_release)]), halt()."],
            "elixir": ["elixir", "--version"],
            "rebar3": ["rebar3", "--version"]
        }
    elif platform == "jvm":
        commands = {
            "java": ["java", "-version"],
            "maven": ["mvn", "--version"],
            "gradle": ["gradle", "--version"],
            "async-profiler": ["/opt/async-profiler/bin/asprof", "--version"]
        }
    elif platform == "dotnet":
        commands = {
            "dotnet": ["dotnet", "--version"],
            "dotnet-trace": ["dotnet-trace", "--version"]
        }
    else:
        return versions

    # Run each command in the container
    for tool, cmd in commands.items():
        try:
            result = run_command([
                "docker", "run", "--rm",
                "--platform", get_current_platform(),
                temp_tag
            ] + cmd, check=False)

            if result.returncode == 0:
                version = result.stdout.strip()
                # Clean up version strings
                if tool == "uv":
                    # uv 0.4.18 -> 0.4.18
                    version = version.replace("uv ", "")
                elif tool == "py-spy":
                    # py-spy 0.3.14 -> 0.3.14
                    version = version.replace("py-spy ", "")
                elif tool == "0x":
                    # 0x v5.5.0 -> 5.5.0
                    version = version.replace("0x ", "").replace("v", "")
                elif tool == "nvm" or tool == "rbenv":
                    # Just take the version number
                    version = version.split()[0]
                elif tool == "rbspy":
                    # rbspy 0.18.1 -> 0.18.1
                    version = version.replace("rbspy ", "")
                elif tool == "php":
                    # PHP 8.2.10 (cli) (built: ...) -> 8.2.10
                    lines = version.split('\n')
                    if lines:
                        match = lines[0].split()[1] if ' ' in lines[0] else lines[0]
                        version = match
                elif tool == "composer":
                    # Composer version 2.6.5 2023-10-06 10:11:52 -> 2.6.5
                    parts = version.split()
                    if len(parts) >= 3 and parts[0] == "Composer":
                        version = parts[2]
                elif tool == "excimer":
                    # Version string is already clean from phpversion()
                    version = version.strip()
                elif tool == "perf":
                    # perf version 6.16.0 -> 6.16.0
                    version = version.replace("perf version ", "")
                elif tool == "binutils":
                    # GNU objdump (GNU Binutils for Ubuntu) 2.38 -> 2.38
                    lines = version.split('\n')
                    if lines:
                        parts = lines[0].split()
                        # Find the version number (usually the last part)
                        for part in reversed(parts):
                            if '.' in part and part[0].isdigit():
                                version = part
                                break
                elif tool == "erlang":
                    # OTP release number like "27" -> 27
                    version = version.strip()
                elif tool == "elixir":
                    # Elixir 1.18.0 (compiled with Erlang/OTP 27) -> 1.18.0
                    lines = version.split('\n')
                    if lines:
                        parts = lines[0].split()
                        if len(parts) >= 2 and parts[0] == "Elixir":
                            version = parts[1]
                elif tool == "rebar3":
                    # rebar 3.25.0 on Erlang/OTP 27 Erts 14.1.1 -> 3.25.0
                    parts = version.split()
                    if len(parts) >= 2 and parts[0] == "rebar":
                        version = parts[1]
                elif tool == "java":
                    # openjdk version "21.0.2" 2024-01-16 LTS -> 21.0.2
                    # Note: java -version outputs to stderr
                    lines = result.stderr.strip().split('\n') if result.stderr else []
                    if lines and 'version' in lines[0]:
                        import re
                        match = re.search(r'"([^"]+)"', lines[0])
                        if match:
                            version = match.group(1)
                        else:
                            version = lines[0]
                elif tool == "maven":
                    # Apache Maven 3.9.11 (2be...) -> 3.9.11
                    lines = version.split('\n')
                    if lines and 'Apache Maven' in lines[0]:
                        parts = lines[0].split()
                        if len(parts) >= 3:
                            version = parts[2]
                elif tool == "gradle":
                    # Gradle 9.0.0 -> 9.0.0
                    lines = version.split('\n')
                    for line in lines:
                        if line.startswith('Gradle '):
                            version = line.replace('Gradle ', '').strip()
                            break
                elif tool == "async-profiler":
                    # Async-profiler 4.1 built on Jul 21 2025 -> 4.1
                    import re
                    match = re.search(r'Async-profiler (\d+\.\d+)', version)
                    if match:
                        version = match.group(1)
                elif tool == "dotnet":
                    # .NET version is already clean from --version
                    version = version.strip()
                elif tool == "dotnet-trace":
                    # dotnet-trace version might include extra text, extract just the version
                    lines = version.split('\n')
                    if lines:
                        # Look for version pattern in first line
                        import re
                        match = re.search(r'(\d+\.\d+\.\d+)', lines[0])
                        if match:
                            version = match.group(1)
                        else:
                            version = lines[0].strip()

                versions[tool] = version
        except Exception as e:
            print(f"Warning: Could not get version for {tool}: {e}")

    return versions


def generate_description(platform: str, versions: Dict[str, str]) -> str:
    """Generate a description for the container based on installed software."""
    descriptions = {
        "python": "Python profiling environment with uv package manager and py-spy profiler",
        "nodejs": "Node.js profiling environment with nvm version manager and 0x profiler",
        "ruby": "Ruby profiling environment with rbenv version manager and rbspy profiler",
        "php": "PHP profiling environment with Composer package manager and Excimer profiler",
        "native": "Native code profiling environment with perf profiler and binary analysis tools",
        "beam": "BEAM VM (Erlang/Elixir) profiling environment with Linux perf JIT integration",
        "jvm": "JVM profiling environment with async-profiler for Java/Kotlin/Scala applications",
        "dotnet": ".NET profiling environment with dotnet-trace profiler for C#/F#/VB.NET applications"
    }

    base_desc = descriptions.get(platform, f"{platform} profiling environment")

    # Add version info
    version_parts = []
    if platform == "python" and versions:
        if "uv" in versions:
            version_parts.append(f"uv {versions['uv']}")
        if "py-spy" in versions:
            version_parts.append(f"py-spy {versions['py-spy']}")
    elif platform == "nodejs" and versions:
        if "nvm" in versions:
            version_parts.append(f"nvm {versions['nvm']}")
        # Note: 0x is installed by bootstrap script, not Dockerfile
    elif platform == "ruby" and versions:
        if "rbenv" in versions:
            version_parts.append(f"rbenv {versions['rbenv']}")
        if "rbspy" in versions:
            version_parts.append(f"rbspy {versions['rbspy']}")
    elif platform == "php" and versions:
        if "php" in versions:
            version_parts.append(f"PHP {versions['php']}")
        if "composer" in versions:
            version_parts.append(f"Composer {versions['composer']}")
        if "excimer" in versions:
            version_parts.append(f"Excimer {versions['excimer']}")
    elif platform == "native" and versions:
        if "perf" in versions:
            version_parts.append(f"perf {versions['perf']}")
        if "binutils" in versions:
            version_parts.append(f"binutils {versions['binutils']}")
    elif platform == "beam" and versions:
        if "erlang" in versions:
            version_parts.append(f"Erlang/OTP {versions['erlang']}")
        if "elixir" in versions:
            version_parts.append(f"Elixir {versions['elixir']}")
        if "rebar3" in versions:
            version_parts.append(f"Rebar3 {versions['rebar3']}")
    elif platform == "jvm" and versions:
        if "java" in versions:
            version_parts.append(f"OpenJDK {versions['java']}")
        if "maven" in versions:
            version_parts.append(f"Maven {versions['maven']}")
        if "gradle" in versions:
            version_parts.append(f"Gradle {versions['gradle']}")
        if "async-profiler" in versions:
            version_parts.append(f"async-profiler {versions['async-profiler']}")
    elif platform == "dotnet" and versions:
        if "dotnet" in versions:
            version_parts.append(f".NET {versions['dotnet']}")
        if "dotnet-trace" in versions:
            version_parts.append(f"dotnet-trace {versions['dotnet-trace']}")

    if version_parts:
        return f"{base_desc}. Includes {', '.join(version_parts)}."
    else:
        return base_desc


def get_current_platform() -> str:
    """Get the current platform for docker commands."""
    machine = platform.machine().lower()
    if machine in ["x86_64", "amd64"]:
        return "linux/amd64"
    elif machine in ["aarch64", "arm64"]:
        return "linux/arm64"
    else:
        return "linux/amd64"  # Default to amd64


def clean_existing_images(platform_name: str, tag: Optional[str] = None) -> None:
    """Remove existing local containers and images for the platform."""
    image_tag = f"{REGISTRY}-{platform_name}:{tag or 'latest'}"
    # Match the temporary tag pattern used during build
    temp_tag = f"uniprof-{platform_name}:temp-build-{tag or 'latest'}"

    print(f"\nCleaning up existing images for {platform_name}...")

    # Get list of running containers using this image
    try:
        result = run_command([
            "docker", "ps", "-a", "-q",
            "--filter", f"ancestor={image_tag}"
        ], check=False)

        if result.returncode == 0 and result.stdout.strip():
            container_ids = result.stdout.strip().split('\n')
            print(f"Found {len(container_ids)} containers using {image_tag}")

            # Stop and remove containers
            for container_id in container_ids:
                print(f"Removing container {container_id}")
                run_command(["docker", "rm", "-f", container_id], check=False)
    except Exception as e:
        print(f"Warning: Error checking for containers: {e}")

    # Remove the images
    for tag in [image_tag, temp_tag]:
        try:
            # Check if image exists
            result = run_command(["docker", "images", "-q", tag], check=False)
            if result.returncode == 0 and result.stdout.strip():
                print(f"Removing image {tag}")
                run_command(["docker", "rmi", "-f", tag], check=False)
        except Exception as e:
            print(f"Warning: Error removing image {tag}: {e}")

    # Also check for any dangling images with our labels
    try:
        result = run_command([
            "docker", "images", "-q",
            "--filter", "dangling=true",
            "--filter", f"label=org.opencontainers.image.source=https://github.com/indragiek/uniprof"
        ], check=False)

        if result.returncode == 0 and result.stdout.strip():
            image_ids = result.stdout.strip().split('\n')
            print(f"Found {len(image_ids)} dangling uniprof images")
            for image_id in image_ids:
                print(f"Removing dangling image {image_id}")
                run_command(["docker", "rmi", "-f", image_id], check=False)
    except Exception as e:
        print(f"Warning: Error removing dangling images: {e}")


def annotate_manifest(image_tag: str, description: str) -> bool:
    """Add description annotation to the manifest for multi-arch images."""
    print(f"\nAdding description annotation to manifest...")

    try:
        # First, we need to enable experimental CLI features for manifest commands
        # Set the environment variable for this command
        env = os.environ.copy()
        env['DOCKER_CLI_EXPERIMENTAL'] = 'enabled'

        # Inspect the manifest to ensure it exists
        inspect_cmd = ["docker", "manifest", "inspect", image_tag]
        result = subprocess.run(inspect_cmd, capture_output=True, text=True, env=env)
        if result.returncode != 0:
            print(f"Warning: Could not inspect manifest for {image_tag}")
            # Try with buildx imagetools instead
            pass

        # Create a new manifest with annotations using buildx imagetools
        # This is more reliable than docker manifest annotate
        annotate_cmd = [
            "docker", "buildx", "imagetools", "create",
            "--annotation", f"index:org.opencontainers.image.description={description}",
            "-t", image_tag,
            image_tag  # Source and destination are the same to update in place
        ]

        result = run_command(annotate_cmd, check=False)
        if result.returncode == 0:
            print("Successfully added description annotation to manifest")
            return True
        else:
            print(f"Warning: Could not annotate manifest: {result.stderr if result.stderr else 'Unknown error'}")
            return False

    except Exception as e:
        print(f"Warning: Error annotating manifest: {e}")
        return False


def build_multiarch_container(platform_name: str, tag: Optional[str] = None, push: bool = False, skip_cleanup: bool = False) -> Tuple[bool, Optional[Dict[str, str]]]:
    """Build a multi-architecture container for the specified platform."""
    if platform_name not in SUPPORTED_PLATFORMS:
        print(f"Error: Unsupported platform '{platform_name}'. Supported: {', '.join(SUPPORTED_PLATFORMS)}")
        return False, None

    # Clean up existing images first unless skipped
    if not skip_cleanup:
        clean_existing_images(platform_name, tag)

    # Get the project root directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    dockerfile_path = project_root / "containers" / platform_name / "Dockerfile"
    context_path = project_root / "containers" / platform_name

    if not dockerfile_path.exists():
        print(f"Error: Dockerfile not found at {dockerfile_path}")
        return False, None

    # Build the image tag
    image_tag = f"{REGISTRY}-{platform_name}:{tag or 'latest'}"
    # Use a local-only tag for temporary image to prevent accidental pushes
    temp_tag = f"uniprof-{platform_name}:temp-build-{tag or 'latest'}"

    # First, build a temporary image for the current platform to extract version info
    # IMPORTANT: The temp_tag does NOT include the registry prefix to prevent accidental pushes
    print(f"\nBuilding temporary image to extract version information...")
    build_cmd = [
        "docker", "buildx", "build",
        "--platform", get_current_platform(),
        "-t", temp_tag,
        "--label", f"org.opencontainers.image.source=https://github.com/indragiek/uniprof",
        "-f", str(dockerfile_path),
        "--load",  # Load into local docker only
        str(context_path)
    ]

    try:
        result = run_command(build_cmd, stream_output=True)
        if result.returncode != 0:
            print(f"\nError building temporary container")
            return False, None
    except subprocess.CalledProcessError:
        print(f"\nError building temporary container")
        return False, None

    # Extract version information
    print(f"\nExtracting version information from container...")
    versions = get_version_info(platform_name, temp_tag)

    # Generate description
    description = generate_description(platform_name, versions)
    print(f"\nGenerated description: {description}")
    print(f"Version info: {json.dumps(versions, indent=2)}")

    # Build the final multi-arch image with all labels
    print(f"\nBuilding final multi-architecture image...")
    build_cmd = [
        "docker", "buildx", "build",
        "--platform", ",".join(ARCHITECTURES),
        "-t", image_tag,
        "--label", f"org.opencontainers.image.source=https://github.com/indragiek/uniprof",
        "--label", f"org.opencontainers.image.description={description}",
        "-f", str(dockerfile_path),
        # Disable attestations to reduce the number of images pushed
        "--provenance=false",
        "--sbom=false"
    ]

    # Add version-specific labels
    for tool, version in versions.items():
        build_cmd.extend(["--label", f"com.github.indragiek.uniprof.{tool}.version={version}"])

    # Add output type
    if push:
        build_cmd.append("--push")
        print("\nNote: Multi-arch builds will create multiple images in the registry:")
        print("  - 1 manifest list (tagged as 'latest' or your specified tag)")
        print(f"  - {len(ARCHITECTURES)} architecture-specific images (untagged SHA hashes)")
        print("This is normal behavior for multi-architecture container images.")
    else:
        # For local builds, we can only load single-platform images
        print("Note: Multi-platform images cannot be loaded locally. Use --push to push to registry.")
        build_cmd.extend(["--platform", get_current_platform(), "--load"])

    build_cmd.append(str(context_path))

    try:
        result = run_command(build_cmd, stream_output=True)
        if result.returncode == 0:
            print(f"\nSuccessfully built {image_tag}")

            # If we pushed the image, add description annotation to the manifest
            if push:
                annotate_manifest(image_tag, description)

            # Clean up temporary image
            try:
                run_command(["docker", "rmi", temp_tag], check=False)
            except:
                pass

            return True, versions
        else:
            print(f"\nError building container")
            return False, None
    except subprocess.CalledProcessError:
        print(f"\nError building container")
        return False, None


def check_docker() -> bool:
    """Check if Docker is installed and running."""
    try:
        result = run_command(["docker", "version"], check=False)
        if result.returncode != 0:
            print("Error: Docker is not installed or not running")
            print("Please install Docker and ensure the Docker daemon is running")
            return False
        return True
    except FileNotFoundError:
        print("Error: Docker command not found")
        print("Please install Docker from https://docs.docker.com/get-docker/")
        return False


def update_docker_utils() -> None:
    """Update docker.ts to specify architecture when pulling images."""
    print("\nUpdating docker utils to specify architecture...")

    docker_utils_path = Path(__file__).parent.parent / "src" / "utils" / "docker.ts"

    if not docker_utils_path.exists():
        print(f"Warning: Could not find {docker_utils_path}")
        return

    # Read the current content
    content = docker_utils_path.read_text()

    # Check if already updated
    if "--platform" in content:
        print("Docker utils already updated to specify platform")
        return

    # Add platform detection function
    platform_detection = '''import * as os from 'os';

/**
 * Get the Docker platform string for the current architecture
 */
function getDockerPlatform(): string {
  const arch = os.arch();
  switch (arch) {
    case 'x64':
    case 'x86_64':
      return 'linux/amd64';
    case 'arm64':
    case 'aarch64':
      return 'linux/arm64';
    default:
      // Default to amd64 for unknown architectures
      return 'linux/amd64';
  }
}

'''

    # Find where to insert the function (after imports)
    import_end = content.rfind('import')
    if import_end != -1:
        # Find the end of the line
        newline_pos = content.find('\n', import_end)
        if newline_pos != -1:
            # Insert the platform detection function
            content = content[:newline_pos + 1] + '\n' + platform_detection + content[newline_pos + 1:]

    # Update the docker pull command to include platform
    content = content.replace(
        'const pullResult = Bun.spawn([\'docker\', \'pull\', image]);',
        'const pullResult = Bun.spawn([\'docker\', \'pull\', \'--platform\', getDockerPlatform(), image]);'
    )

    # Write the updated content
    docker_utils_path.write_text(content)
    print("Updated docker.ts to specify platform when pulling images")


def main():
    parser = argparse.ArgumentParser(
        description="Build UniProf profiler containers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build the Python profiler container
  uv run containers/build_containers.py python

  # Build and push to registry
  uv run containers/build_containers.py python --push

  # Build with a specific tag
  uv run containers/build_containers.py python --tag v1.0.0

  # Build all platforms
  uv run containers/build_containers.py all --push
"""
    )

    parser.add_argument(
        "platform",
        choices=SUPPORTED_PLATFORMS + ["all"],
        help="Platform to build container for (or 'all' for all platforms)"
    )

    parser.add_argument(
        "--push",
        action="store_true",
        help="Push the built images to the GitHub Container Registry"
    )

    parser.add_argument(
        "--tag",
        default="latest",
        help="Tag for the Docker image (default: latest)"
    )

    parser.add_argument(
        "--update-docker-utils",
        action="store_true",
        help="Update docker.ts to specify platform when pulling images"
    )

    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Skip removing existing containers and images before building"
    )

    args = parser.parse_args()

    # Check if Docker is available
    if not check_docker():
        sys.exit(1)

    # Check if Docker buildx is available
    if not check_docker_buildx():
        sys.exit(1)

    # Update docker utils if requested
    if args.update_docker_utils:
        update_docker_utils()

    # Determine which platforms to build
    platforms_to_build = SUPPORTED_PLATFORMS if args.platform == "all" else [args.platform]

    # Build the container(s)
    all_successful = True
    all_versions = {}

    for platform in platforms_to_build:
        print(f"\n{'='*60}")
        print(f"Building {platform} container...")
        print(f"{'='*60}")

        success, versions = build_multiarch_container(platform, args.tag, args.push, args.skip_cleanup)
        if success:
            all_versions[platform] = versions
        else:
            all_successful = False
            if len(platforms_to_build) > 1:
                print(f"Failed to build {platform}, continuing with other platforms...")
            else:
                sys.exit(1)

    if all_successful:
        print("\n" + "="*60)
        print("All containers built successfully!")
        print("="*60)

        # Print summary of versions
        print("\nVersion Summary:")
        for platform, versions in all_versions.items():
            print(f"\n{platform}:")
            for tool, version in versions.items():
                print(f"  {tool}: {version}")

        if args.push:
            print(f"\nImages pushed to {REGISTRY}")
        else:
            print(f"\nImages built locally (current platform only)")
    else:
        print("\nSome containers failed to build")
        sys.exit(1)


if __name__ == "__main__":
    main()
