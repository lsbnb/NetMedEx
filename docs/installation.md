## Web Application (via Docker)

If you have <a href="https://www.docker.com/" target="_blank">Docker</a> installed on your machine, you can run the following command to launch the web application using Docker, then open `localhost:8050` in your browser:

```bash
docker run -p 8050:8050 --rm lsbnb/netmedex
```

## Installation

Install NetMedEx from PyPI to use the web application locally or access the CLI:

```bash
pip install netmedex
```

*We recommend using Python version >= 3.11 for NetMedEx.*

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