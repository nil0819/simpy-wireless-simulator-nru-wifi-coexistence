# Rashed-Step 6.B-07-31-2026-start
# Licensed 5G NR UE (as opposed to nru.ue.NrUE, which belongs to the
# unlicensed NR-U path). Same shape as NrUE - kept as a separate class
# rather than reusing NrUE so the two technologies stay decoupled (a
# licensed-NR run never accidentally shares UE objects/state with an
# NR-U run), matching how wifi/nru already have their own independent
# device classes.

from dataclasses import dataclass
from common.common import Pos
from typing import Optional, Any


@dataclass
class NrUeLicensed:
    name: str
    pos: Pos  # initial/static position - if mobility is set, use current_pos() instead
    gnb_name: str  # associated gNB
    mobility: Optional[Any] = None

    def current_pos(self) -> Pos:
        return self.mobility.pos_now() if self.mobility is not None else self.pos
# Rashed-Step 6.B-07-31-2026-end
