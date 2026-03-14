from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from .client import YuqueClient

ParserConfigurator = Callable[[argparse.ArgumentParser], None]
CommandHandler = Callable[[YuqueClient, argparse.Namespace], Any]
OperationDispatcher = Callable[[YuqueClient, Dict[str, Any]], Any]


@dataclass(frozen=True)
class CommandSpec:
    name: str
    help: str
    handler: CommandHandler
    configure: Optional[ParserConfigurator] = None
    defaults: Dict[str, Any] = field(default_factory=dict)
