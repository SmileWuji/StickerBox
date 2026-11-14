import argparse
import json
import os
import sys
from collections.abc import Callable

from . import __version__
from .errors import EXIT_ERROR, EXIT_OK, EXIT_USAGE, BoxError

Handler = Callable[[argparse.Namespace], dict]


class _Parser(argparse.ArgumentParser):
    """Long options must be written in full, so a caller that filters options by name (a wrapper
    refusing --box, say) cannot be bypassed with a prefix such as --bo."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("allow_abbrev", False)
        super().__init__(*args, **kwargs)

    def error(self, message):
        raise BoxError("usage", f"{self.prog}: {message}", exit_code=EXIT_USAGE)


def _common() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--box", default=argparse.SUPPRESS, help="box directory (else $STICKER_BOX_DIR, else the current directory)")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS, help="print JSON (also $STICKER_BOX_JSON=1)")
    return common


def build_parser() -> argparse.ArgumentParser:
    common = _common()
    parser = _Parser(prog="sticker-box", parents=[common], description="Keep a directory of images with a SQLite index, a manual and a policy.")
    parser.add_argument("--version", action="version", version=f"sticker-box {__version__}")
    sub = parser.add_subparsers(dest="command", metavar="<command>", parser_class=_Parser)
    from . import commands

    commands.register(sub, common)
    return parser


def json_wanted(argv: list[str], args: argparse.Namespace | None = None) -> bool:
    if args is not None and getattr(args, "json", False):
        return True
    if "--json" in argv:
        return True
    return os.environ.get("STICKER_BOX_JSON", "") not in ("", "0")


def render_text(value, indent: int = 0) -> str:
    pad = "  " * indent
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if item is None or item == [] or item == {}:
                continue
            if isinstance(item, dict) or (isinstance(item, list) and any(isinstance(x, (dict, list)) for x in item)):
                lines.append(f"{pad}{key}:")
                lines.append(render_text(item, indent + 1))
            elif isinstance(item, list):
                lines.append(f"{pad}{key}: {', '.join(str(x) for x in item)}")
            else:
                lines.append(f"{pad}{key}: {item}")
        return "\n".join(line for line in lines if line)
    if isinstance(value, list):
        blocks = []
        for item in value:
            if isinstance(item, dict):
                body = render_text(item, indent + 1)
                blocks.append(f"{pad}-\n{body}" if body else f"{pad}-")
            else:
                blocks.append(f"{pad}- {item}")
        return "\n".join(blocks)
    return f"{pad}{value}"


def emit(result: dict, as_json: bool, stream=None) -> None:
    stream = stream or sys.stdout
    if as_json:
        stream.write(_safe(json.dumps(result, ensure_ascii=False, indent=2)) + "\n")
    else:
        text = result.get("_text") if isinstance(result.get("_text"), str) else render_text({k: v for k, v in result.items() if k != "_text"})
        if text:
            stream.write(_safe(text) + "\n")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = None
    try:
        parser = build_parser()
        args = parser.parse_args(argv)
        if not getattr(args, "command", None):
            parser.print_help()
            return EXIT_OK
        result = args.handler(args)
        code = result.pop("_exit", EXIT_OK)
        as_json = json_wanted(argv, args)
        if as_json:
            result.pop("_text", None)
        emit(result, as_json)
        return code
    except BoxError as err:
        emit_error(err, json_wanted(argv, args))
        return err.exit_code
    except KeyboardInterrupt:
        return EXIT_ERROR
    except Exception as err:
        emit_error(unexpected(err), json_wanted(argv, args))
        return EXIT_ERROR
    finally:
        from . import commands

        commands.close_all()


def unexpected(err: Exception) -> BoxError:
    """Errors the tool did not anticipate still come out as {"error": ...}, never a traceback."""
    import sqlite3

    if isinstance(err, sqlite3.OperationalError) and "locked" in str(err):
        return BoxError("busy", "another session held the box for too long; try again")
    if isinstance(err, sqlite3.DatabaseError):
        return BoxError("corrupt_box", f"box.sqlite3 cannot be read as a box ({err})")
    if isinstance(err, OSError):
        return BoxError("os_error", f"{err.strerror or type(err).__name__}")
    if isinstance(err, UnicodeError):
        return BoxError("encoding", "an argument or file name is not valid UTF-8")
    return BoxError("internal", f"unexpected {type(err).__name__}; please report it")


def _safe(text: str) -> str:
    return text.encode("utf-8", "replace").decode("utf-8")


def emit_error(err: BoxError, as_json: bool) -> None:
    if as_json:
        sys.stdout.write(_safe(json.dumps(err.to_dict(), ensure_ascii=False, indent=2)) + "\n")
    else:
        sys.stderr.write(_safe(f"error ({err.code}): {err.message}") + "\n")
        details = render_text(err.details, 1)
        if details:
            sys.stderr.write(_safe(details) + "\n")


if __name__ == "__main__":
    sys.exit(main())
