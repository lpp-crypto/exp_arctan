import argparse
from sys import argv

from typing import Any, Dict, Optional, Sequence
from .transcript import VERBOSE_TABLE


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


def get_cli_args(
        parameters: list[tuple],
        title: str,
        description: str=""
) -> argparse.Namespace:
    """Builds an ArgumentParser, parses the CLI arguments, and returns a Namespace with one attribute per key. The input is a list of the form [(variable_name, default_value, "description")].
    

    Type inference rules, applied per entry based on type(default_value):
      - bool          -> parsed via _str2bool (accepts true/false/yes/no/1/0)
      - None          -> parsed as str (no type info available from a None
                         default; override by passing an explicit non-None
                         placeholder if you need int/float parsing instead)
      - list / tuple  -> parsed with nargs="*", element type taken from the
                         first element of the default (empty list -> str)
      - anything else -> parsed with type(default_value) directly
                         (int, float, str, Path, etc. all work this way)

    """
    current_params = [entry[0] for entry in parameters]
    if "verbose" not in current_params:
        desc = "Decide how verbose the output is. Must be one of \""
        desc += "\", \"".join(VERBOSE_TABLE.keys()) + "\""
        parameters.append(("verbose", "normal", desc))
    if "early_abort" not in current_params:
        desc = "If set, the program terminates at the first \"FAIL\"."
        parameters.append(("early_abort", False, desc))
                         
    parser = argparse.ArgumentParser(description=description)

    for entry in parameters:
        name = entry[0]
        default = entry[1] 
        var_description = entry[2] if len(entry) > 2 else ""
        var_description += f" (defaults to \"{default}\")"
        flag = f"-{name}"
        if isinstance(default, bool): # Claude insists this particular case is needed
            parser.add_argument(
                flag,
                type=_str2bool,
                default=default,
                metavar="{true,false}",
                help=var_description
            )
        elif default is None:
            parser.add_argument(
                flag,
                type=str,
                default=None,
                help=var_description
            )
        elif isinstance(default, (list, tuple)):
            elem_type = type(default[0]) if len(default) > 0 else str
            parser.add_argument(
                flag,
                type=elem_type,
                nargs="*",
                default=list(default),
                help=var_description
            )
        else:
            parser.add_argument(
                flag,
                type=type(default),
                default=default,
                help=var_description
            )

    return parser.parse_args(argv[1:])


