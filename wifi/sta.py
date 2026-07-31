# Rashed-Step 1.B_1-12-26-2025-start

from dataclasses import dataclass
from common.common import Pos
# Rashed-Step 5.G-02-06-2026-start
from typing import Optional, Any
# Rashed-Step 5.G-02-06-2026-end


@dataclass
class WiFiSTA:
    name: str
    pos: Pos  # initial/static position - if mobility is set, use current_pos() instead
    ap_name: str  # associated AP
    # Rashed-Step 5.G-02-06-2026-start
    # Optional common_phy.WaypointMobility instance. None (default) = the
    # STA never moves, current_pos() just returns the static pos above -
    # byte-identical to every pre-5.G run.
    mobility: Optional[Any] = None

    def current_pos(self) -> Pos:
        return self.mobility.pos_now() if self.mobility is not None else self.pos
    # Rashed-Step 5.G-02-06-2026-end



# Rashed-Step 1.B_1-12-26-2025-end