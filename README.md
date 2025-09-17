[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/indragiek-uniprof-badge.png)](https://mseep.ai/app/indragiek-uniprof)

# `uniprof`

uniprof simplifies CPU profiling for humans and AI agents. Profile any application without code changes or added dependencies.

```bash
# Profile and analyze any app in one step
npx uniprof python script.py
```

## Table of Contents

- [Supported Platforms](#supported-platforms)
- [System Requirements](#system-requirements)
- [Installation](#installation)
  - [MCP Server](#mcp-server)
- [Quick Start](#quick-start)
  - [Host vs. Container Modes](#host-vs-container-modes)
- [Compiling with Debug Information](#compiling-with-debug-information)
- [Documentation](#documentation)
- [Credits](#credits)
- [License](#license)

## Supported Platforms

uniprof implements a common interface over multiple profilers that specialize in different platforms and runtimes. It automatically detects which profiler to use based on the command being executed, runs the profiler, transforms the varying output formats into a single format, and runs statistical analysis on the data to identify hotspots.

| Platform | Profiler | Container | Host | Min Version |
|----------|----------|-----------|-------|-------------|
| Python | [py-spy](https://github.com/benfred/py-spy) | ✅ | ✅ | Python 3.7+ |
| Node.js | [0x](https://github.com/davidmarkclements/0x) | ✅ | ✅ | Node 14+ |
| Ruby | [rbspy](https://github.com/rbspy/rbspy) | ✅ | ✅ | Ruby 2.5+ |
| PHP | [Excimer](https://github.com/wikimedia/mediawiki-php-excimer) | ✅ | ✅ | PHP 7.2+ |
| JVM | [async-profiler](https://github.com/async-profiler/async-profiler) | ✅ | ✅ | Java 8+ |
| .NET | [dotnet-trace](https://github.com/dotnet/diagnostics) | ✅ | ✅ | .NET 5+ |
| BEAM | [perf](https://perf.wiki.kernel.org) | ✅ | ✅* | OTP 24+ |
| Native (macOS) | [Instruments](https://developer.apple.com/xcode/features/) | ❌ | ✅ | Xcode 14.3+ |
| Native (Linux) | [perf](https://perf.wiki.kernel.org) | ✅ | ✅ | Linux 2.6.31+ |

\* Linux only for host mode

## System Requirements

**tl;dr:** macOS or Linux with Docker installed

uniprof is designed to run on macOS and Linux but has primarily been developed & tested on macOS. If you find any bugs when running on Linux, please [report them](https://github.com/indragiek/uniprof/issues). Running on a Windows host is currenly not supported, but you can run on Linux installed on Windows via [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install). Note that when using uniprof via WSL2, profiling native Windows executables is not supported, but you can still use the profilers for the higher level language runtimes like Python and Node.js.

Profiling tools are often non-trivial to set up correctly and can require [elevated privileges](https://www.kernel.org/doc/html/v6.16/admin-guide/perf-security.html). To simplify set up and provide better isolation for the profiled code, uniprof defaults to using [Docker containers](https://github.com/indragiek?tab=packages&repo_name=uniprof) for each runtime that are pre-configured to run specific profiling tools. uniprof mounts your workspace in the container and executes the program with the profiler attached. uniprof also supports profiling outside the container if the host system has the profiling tools installed by running with the `--mode host` flag. The only case where containerized execution is not supported is when profiling a native Mach-O binary on macOS, since Apple Instruments cannot run inside a container.

## Installation

```bash
npm install -g uniprof
```

### MCP Server

```bash
# Install uniprof MCP server automatically
uniprof mcp install claudecode
uniprof mcp install cursor
uniprof mcp install vscode
```

**Supported clients for auto-installation:** amp, claudecode, codex, cursor, gemini, vscode, zed

If auto-installation is not supported for your client, add an MCP server using the stdio transport with the command `npx -y uniprof mcp run`.

For detailed MCP documentation see [docs/mcp.md](docs/mcp.md).

## Quick Start

**Profile and analyze in one step**:
```bash
# Profile most languages and get immediate analysis
uniprof python app.py
uniprof node server.js
uniprof ruby script.rb
uniprof java -jar myapp.jar
uniprof dotnet MyApp.dll
uniprof ./my-native-app

# Profile and visualize flamegraph in browser
uniprof --visualize python app.py
```

**Save profiles to analyze and visualize later**:
```bash
# 1. Check environment (optional)
uniprof bootstrap

# 2. Record a profile
uniprof record -o profile.json -- python app.py
uniprof record -o profile.json -- node server.js
uniprof record -o profile.json -- ruby script.rb
uniprof record -o profile.json -- php script.php
uniprof record -o profile.json -- java -jar myapp.jar
uniprof record -o profile.json -- ./gradlew run
uniprof record -o profile.json -- ./mvnw spring-boot:run
uniprof record -o profile.json -- dotnet MyApp.dll
uniprof record -o profile.json -- elixir script.exs
uniprof record -o profile.json -- mix run
uniprof record -o profile.json -- ./my-native-app
uniprof record -o profile.json -- /Applications/MyApp.app

# 3. Analyze profile data to find hotspots
uniprof analyze profile.json

# 4. Visualize flamegraph in the browser
uniprof visualize profile.json
```

For detailed command line options documentation see [docs/cli.md](docs/cli.md).

### Host vs. Container Modes

Use the `--mode` option to control how profiling runs:

- **`auto` (default)**: Prefer container mode when Docker is available; otherwise use host.
  - Language runtimes (Python/Node.js/Ruby/PHP/BEAM/JVM/.NET) default to container for zero-setup.
  - Native on macOS with Mach-O binaries uses host (Instruments). ELF binaries on macOS are supported in container mode.
  - Native on Linux defaults to container; host can be used if you prefer your local perf setup.
- **`host`**: Force host-installed profilers.
- **`container`**: Force Docker containers (not supported for macOS Instruments/Mach-O binaries).

```bash
# Auto mode (default)
uniprof record -o profile.json -- python script.py

# Force host profilers
uniprof record --mode host -o profile.json -- python script.py

# Force container mode
uniprof record --mode container -o profile.json -- ./my-linux-app
```

## Compiling with Debug Information

Native profiling requires debug information for meaningful results. Debug symbols enable the profiler to map memory addresses to function names, providing readable output instead of just hexadecimal addresses. Additionally, frame pointers improve call stack accuracy, especially for optimized code.

| Compiler | DWARF Debug Info | Frame Pointers | Notes |
|----------|------------------|----------------|-------|
| **gcc** | `gcc -g -o myapp main.c` | `gcc -fno-omit-frame-pointer -o myapp main.c` | Use `-g3` for maximum debug info, `-ggdb` for GDB-specific extensions |
| **clang** | `clang -g -o myapp main.cpp` | `clang -fno-omit-frame-pointer -o myapp main.cpp` | Use `-gfull` on macOS for complete debug info |
| **swift** | `swiftc -g main.swift` | `swiftc -Xcc -fno-omit-frame-pointer main.swift` | Debug builds include symbols by default with `swift build` |
| **cargo** | `cargo build` (debug mode)<br>`cargo build --release` + `[profile.release]`<br>`debug = true` | `RUSTFLAGS="-C force-frame-pointers=yes" cargo build` | Debug builds include DWARF by default; for release builds, add `debug = true` to Cargo.toml |
| **go** | `go build -gcflags=all="-N -l"` | Built-in, always enabled | Go includes debug info by default; `-gcflags` disables optimizations for better debugging |
| **zig** | `zig build-exe -O Debug main.zig` | `zig build-exe -fno-omit-frame-pointer main.zig` | Use `-O ReleaseSafe` with debug info for optimized builds with symbols |
| **ghc** | `ghc -g -rtsopts main.hs` | `ghc -fno-omit-frame-pointer main.hs` | Use `-prof` for profiling builds; `-rtsopts` enables runtime profiling options |

## Documentation

- **[CLI Reference](docs/cli.md)**
- **[Advanced Usage](docs/advanced.md)**
- **[Platform Guides](docs/platforms/)**
- **[MCP Server](docs/mcp.md)**

## Credits

- [py-spy](https://github.com/benfred/py-spy) (MIT) is used for Python profiling. Included in the [uniprof-python](https://github.com/indragiek/uniprof/pkgs/container/uniprof-python) image.
- [0x](https://github.com/davidmarkclements/0x) (MIT) is used for Node.js profiling. Included in the [uniprof-nodejs](https://github.com/indragiek/uniprof/pkgs/container/uniprof-nodejs) image.
- [rbspy](https://github.com/rbspy/rbspy) (MIT) is used for Ruby profiling. Included in the [uniprof-ruby](https://github.com/indragiek/uniprof/pkgs/container/uniprof-ruby) image.
- [Excimer](https://www.mediawiki.org/wiki/Excimer) (Apache 2.0) is used for PHP profiling. Included in the [uniprof-php](https://github.com/indragiek/uniprof/pkgs/container/uniprof-php) image.
- [async-profiler](https://github.com/async-profiler/async-profiler) (Apache 2.0) is used for JVM profiling. Included in the [uniprof-jvm](https://github.com/indragiek/uniprof/pkgs/container/uniprof-jvm) image.
- [dotnet-trace](https://github.com/dotnet/diagnostics) (MIT) is used for .NET profiling. Included in the [uniprof-dotnet](https://github.com/indragiek/uniprof/pkgs/container/uniprof-dotnet) image.
- [perf](https://perfwiki.github.io/main/) (GPL) is used for native profiling on Linux. Included in the [uniprof-native](https://github.com/indragiek/uniprof/pkgs/container/uniprof-native) and [uniprof-beam](https://github.com/indragiek/uniprof/pkgs/container/uniprof-beam) images.
- [speedscope](https://github.com/jlfwong/speedscope) (MIT) is bundled with uniprof and used for flamegraph visualization

## License

All uniprof source code in this repository is licensed under the **MIT License**. See `LICENSE`.

uniprof downloads and runs [Docker images](https://github.com/indragiek?tab=packages&repo_name=uniprof) that bundle third-party software. The Dockerfiles used to build these images can be found in `containers/`. These images and their contents are not covered by the MIT license and are governed by their own licenses. uniprof does not grant rights to those components and does not relicense them.
