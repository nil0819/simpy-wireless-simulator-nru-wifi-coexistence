# Rashed-Step 1.B_2-12-26-2025-start

from dataclasses import dataclass
from common.common import Pos
# Rashed-Step 5.G-02-06-2026-start
from typing import Optional, Any
# Rashed-Step 5.G-02-06-2026-end

@dataclass
class NrUE:
    name: str
    pos: Pos  # initial/static position - if mobility is set, use current_pos() instead
    gnb_name: str  # associated gNB
    # Rashed-Step 5.G-02-06-2026-start
    # See wifi.sta.WiFiSTA.mobility - same idea. None (default) = static,
    # byte-identical to every pre-5.G run.
    mobility: Optional[Any] = None

    def current_pos(self) -> Pos:
        return self.mobility.pos_now() if self.mobility is not None else self.pos
    # Rashed-Step 5.G-02-06-2026-end

# Rashed-Step 1.B_2-12-26-2025-end