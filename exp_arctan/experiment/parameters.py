"""
args_from_defaults.py

Given a dict of {variable_name: default_value}, sets up an argparse parser
that exposes each key as a --variable_name command-line flag, typed
according to the default value, and falling back to that default when the
flag is absent.

Two entry points:
  - build_args(defaults)      -> argparse.Namespace (cfg.variable_name)
  - inject_globals(defaults)  -> also writes each variable directly into
                                  the caller's global namespace, so you can
                                  write `variable_name` as a bare name
                                  afterwards (convenient for quick scripts,
                                  at the cost of being implicit/magic).
"""

from __future__ import annotations

import argparse
import inspect
from typing import Any, Dict, Optional, Sequence


def _str2bool(value: str) -> bool:
    """Type-caster for bool defaults: argparse's own `type=bool` is broken
    (bool("False") == True), so booleans need this explicit parser instead
    of relying on the raw type() of the default."""
    if isinstance(value, bool):
        return value
    lowered = value.lower()
    if lowered in ("yes", "true", "t", "1"):
        return True
    if lowered in ("no", "false", "f", "0"):
        return False
    raise argparse.ArgumentTypeError(
        f"boolean value expected (true/false), got {value!r}"
    )


def build_args(
    defaults: Dict[str, Any],
    description: Optional[str] = None,
    args: Optional[Sequence[str]] = None,
) -> argparse.Namespace:
    """
    Build an ArgumentParser from a {variable_name: default_value} dict and
    parse it, returning a Namespace with one attribute per key.

    Type inference rules, applied per entry based on type(default_value):
      - bool          -> parsed via _str2bool (accepts true/false/yes/no/1/0)
      - None          -> parsed as str (no type info available from a None
                         default; override by passing an explicit non-None
                         placeholder if you need int/float parsing instead)
      - list / tuple  -> parsed with nargs="*", element type taken from the
                         first element of the default (empty list -> str)
      - anything else -> parsed with type(default_value) directly
                         (int, float, str, Path, etc. all work this way)

    `args` is passed straight through to parser.parse_args(); leave it None
    to parse sys.argv as usual (mainly useful for testing with an explicit
    argv list instead of the real command line).
    """
    parser = argparse.ArgumentParser(description=description)

    for name, default in defaults.items():
        flag = f"--{name}"

        if isinstance(default, bool):
            parser.add_argument(
                flag, type=_str2bool, default=default, metavar="{true,false}"
            )
        elif default is None:
            parser.add_argument(flag, type=str, default=None)
        elif isinstance(default, (list, tuple)):
            elem_type = type(default[0]) if len(default) > 0 else str
            parser.add_argument(
                flag, type=elem_type, nargs="*", default=list(default)
            )
        else:
            parser.add_argument(flag, type=type(default), default=default)

    return parser.parse_args(args)


def inject_globals(
    defaults: Dict[str, Any],
    description: Optional[str] = None,
    args: Optional[Sequence[str]] = None,
) -> argparse.Namespace:
    """
    Same as build_args, but also writes each resulting value directly into
    the *caller's* global namespace, so e.g. `defaults = {"n_trials": 10}`
    followed by `inject_globals(defaults)` makes a bare `n_trials` name
    available in the calling module -- no `cfg.n_trials` needed.

    This uses frame introspection to reach the caller's globals(); it only
    works correctly when called directly from the top level of a script
    (not from inside a function you intend to reuse elsewhere), since it
    mutates whatever module happens to be one frame up. Prefer build_args()
    if you want something less implicit / more testable.
    """
    namespace = build_args(defaults, description=description, args=args)
    caller_globals = inspect.stack()[1].frame.f_globals
    caller_globals.update(vars(namespace))
    return namespace
