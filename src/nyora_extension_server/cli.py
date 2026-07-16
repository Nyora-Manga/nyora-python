"""``nyora-extension-server`` command line.

    nyora-extension-server              # run the engine (default port 8788)
    nyora-extension-server --port 9000  # a specific port
    nyora-extension-server --jar path   # use a different engine jar
    nyora-extension-server info         # show jar / java / port-file paths
    nyora-extension-server version
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .server import EngineError, bundled_jar, default_port_file, find_java, serve


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nyora-extension-server",
        description="Run the Nyora parser engine locally so the `nyora` SDK/CLI/TUI "
        "can use your own server instead of the cloud.",
    )
    p.add_argument("--port", type=int, default=None, help="port to serve on (default 8788, or a free port if busy)")
    p.add_argument("--jar", default=None, help="path to an alternative engine jar (default: bundled)")
    p.add_argument("--java", default=None, help="java executable to use (default: $JAVA / $JAVA_HOME / PATH)")
    p.add_argument("--heap", default="1g", help="JVM max heap, e.g. 512m, 2g (default 1g)")
    p.add_argument("--proxy", default=None, help="SOCKS5 proxy for source fetches, e.g. socks5://127.0.0.1:40000 (a WARP exit)")
    p.add_argument("--no-port-file", action="store_true", help="don't write the SDK auto-discovery port file")
    p.add_argument("-q", "--quiet", action="store_true", help="suppress startup logs")

    sub = p.add_subparsers(dest="command", metavar="command")
    sub.add_parser("info", help="show engine jar / java / port-file locations")
    sub.add_parser("version", help="show version")
    return p


def _cmd_info() -> int:
    jar = bundled_jar()
    print(f"version:    {__version__}")
    print(f"engine jar: {jar} ({'present' if jar.exists() else 'MISSING'})")
    print(f"java:       {find_java() or 'NOT FOUND — install a JRE 17+'}")
    print(f"port file:  {default_port_file()}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "version":
        print(__version__)
        return 0
    if args.command == "info":
        return _cmd_info()
    try:
        return serve(
            port=args.port,
            jar=args.jar,
            java=args.java,
            heap=args.heap,
            proxy=args.proxy,
            write_port_file=not args.no_port_file,
            quiet=args.quiet,
        )
    except EngineError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
