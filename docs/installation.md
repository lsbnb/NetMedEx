## Web Application (via Docker)

If you have <a href="https://www.docker.com/" target="_blank">Docker</a> installed on your machine, you can run the following command to launch the web application using Docker, then open `localhost:8050` in your browser:

```bash
docker run -p 8050:8050 --rm lsbnb/netmedex
```

> **Windows users**: Docker is the recommended and most reliable way to run NetMedEx on Windows. See [Windows Installation Notes](#windows-installation-notes) for details.

## Installation

Install the **latest version** directly from GitHub to use the web application locally or access the CLI or Python API:

```bash
pip install git+https://github.com/lsbnb/NetMedEx.git
```

_We recommend using Python version >= 3.11 for NetMedEx._

## Web Application (Local)

After installing NetMedEx, run the following command and open `localhost:8050` in your browser:

```bash
netmedex run
```

## Command-Line Interface (CLI)

After installing NetMedEx, refer to [CLI guides](cli_guides.md) to use the following commands to search articles and generate networks:

```bash
netmedex search  # Search articles
netmedex network  # Generate networks from the output file produced by `netmedex search`
```

## Windows Installation Notes

### Recommended: Use Docker

**Docker is the recommended installation method for Windows users.** The `pip install` approach on Windows requires additional manual configuration and may still encounter system-level limitations (e.g., firewall socket restrictions) that prevent the Graph Panel from working correctly.

```bash
docker run -p 8050:8050 --rm lsbnb/netmedex
```

### pip install on Windows (Advanced)

`pip install` on Windows is supported but requires the following additional steps. If any step fails, use Docker instead.

#### Step 1 — Python version

Use **Python 3.11 or 3.12**. Python 3.13 is supported from NetMedEx v1.3.1 onwards.

#### Step 2 — Add Scripts directory to PATH

After `pip install`, the `netmedex` executable is placed in a directory that may not be on your PATH:

```text
C:\Users\<username>\AppData\Roaming\Python\Python3xx\Scripts\
```

Add this directory to your system PATH via **System Properties → Advanced → Environment Variables**, or run NetMedEx directly with:

```bat
python -m netmedex run
```

#### Step 3 — Set UTF-8 encoding (non-English Windows)

On non-English Windows (e.g., Traditional Chinese locale), set `PYTHONUTF8=1` **before** starting NetMedEx. This prevents encoding errors in third-party libraries when file paths or system messages contain non-ASCII characters:

```bat
set PYTHONUTF8=1
netmedex run
```

To make this permanent, add `PYTHONUTF8=1` to your user environment variables.

> **Note**: Setting `PYTHONUTF8` inside a Python script has no effect — it must be set in the environment before Python launches.

#### Step 4 — Allow port 8050 through Windows Firewall

Windows Firewall may block the webapp port (default: 8050). If you see a socket permission error on startup, allow port 8050 through the firewall or run the terminal as Administrator.

If the Graph Panel remains blank after completing all steps above, switch to the Docker deployment — socket restrictions in some Windows environments cannot be resolved at the application level.
