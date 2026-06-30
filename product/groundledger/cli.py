"""GroundLedger command-line interface.

Installed entry point (after `pip install -e .`):  groundledger <command> ...
No-install equivalent:                              python -m product.groundledger.cli <command> ...

Commands:
  verify                      reproducibility + tamper self-check (offline)
  replay <data_root> <tenant> independently re-attest a stored tenant's ledger
  export build <data_root> <tenant> [--out f --html f --key K]
  export verify <bundle.json> [--key K]
  serve                       run the in-VPC HTTP API (env-configured)
  demo                        run the end-to-end demo (run from the repo checkout)
"""
from __future__ import annotations

import sys

USAGE = __doc__


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(USAGE)
        return 2
    if argv[0] in ("-h", "--help"):
        print(USAGE)
        return 0

    command, rest = argv[0], argv[1:]

    if command == "verify":
        from . import verification
        return verification._main(rest)
    if command == "replay":
        from . import replay
        return replay._main(rest)
    if command == "export":
        from . import export
        return export._main(rest)
    if command == "serve":
        from . import api
        server = api._serve_from_env()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.shutdown()
        return 0
    if command == "demo":
        from product.demo import main as demo_main
        return demo_main()

    print(f"unknown command: {command!r}\n")
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
