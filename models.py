"""Data models for the BAP + QCAP port terminal optimization."""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Dict, Optional



class CraneType(str, Enum):
    STS = "STS"
    MHC = "MHC"


class ProductivityMode(str, Enum):
    MIN = "MIN"
    MAX = "MAX"
    INTERMEDIATE = "INTERMEDIATE"


@dataclass
class Crane:
    """A quay crane."""
    id: str  # Unique identifier
    name: str
    crane_type: CraneType
    berth_range_start: int  # Start of coverage (meters)
    berth_range_end: int    # End of coverage (meters)
    min_productivity: int   # Moves per shift
    max_productivity: int   # Moves per shift


from datetime import datetime, timedelta

@dataclass
class Shift:
    """Represents a specific operational shift."""
    id: int # global index 0..N
    start_time: datetime
    end_time: datetime
    
    @property
    def duration_hours(self) -> float:
        return (self.end_time - self.start_time).total_seconds() / 3600.0
    
    def __str__(self) -> str:
        return f"{self.start_time.strftime('%d%m%Y-%H%M')}"
    
    def __repr__(self) -> str:
        return self.__str__()


@dataclass
class Vessel:
    """A vessel (ship) that needs berth allocation and crane assignment."""

    name: str
    workload: int  # M_i: total container movements needed
    loa: int  # Length Over All in meters
    draft: float  # Required depth for mooring
    arrival_time: datetime  # ETW (Desired arrival)
    departure_deadline: Optional[datetime] = None  # ETC (Desired completion) - Now optional/calculated
    max_cranes: int = 3  # Max cranes that fit on the vessel
    productivity_preference: ProductivityMode = ProductivityMode.INTERMEDIATE
    
    available_shifts: Optional[List[int]] = None 
    
    # Computed at runtime
    arrival_shift_index: int = -1
    arrival_fraction: float = 0.0 # Portion of arrival shift available
    departure_shift_index: int = -1


@dataclass
class ForbiddenZone:
    """A zone on the quay that is restricted during certain shifts (e.g. maintenance)."""

    start_berth_position: int
    end_berth_position: int
    start_shift: int
    end_shift: int  # Exclusive
    description: str = "Maintenance" 


@dataclass
class Berth:
    """The quay/berth where vessels are moored."""

    length: int  # Total length in meters
    depth: float | None = None  # Uniform depth (if constant)
    depth_map: Dict[int, float] | None = None  # Position -> depth (variable)

    def get_depth_at(self, position: int) -> float:
        """Return the depth at a given position along the berth."""
        if self.depth is not None:
            return self.depth
        if self.depth_map is not None:
            # Find the depth segment that covers this position
            sorted_positions = sorted(self.depth_map.keys())
            result = 0.0
            for p in sorted_positions:
                if p <= position:
                    result = self.depth_map[p]
                else:
                    break
            return result
        return float("inf")


@dataclass
class Problem:
    """Full problem instance for BAP + QCAP optimization."""

    berth: Berth
    vessels: List[Vessel]
    cranes: List[Crane]
    shifts: List[Shift]  # Specific shifts in the planning horizon
    # Availability: Map shift_index (0 to N-1) -> List of crane_ids available
    crane_availability_per_shift: Dict[int, List[str]]
    forbidden_zones: List[ForbiddenZone] = field(default_factory=list)

    @property
    def num_shifts(self) -> int:
        return len(self.shifts)


@dataclass
class VesselSolution:
    """Solution for a single vessel."""

    vessel_name: str
    berth_position: int  # Starting meter on the berth
    start_shift: int
    end_shift: int  # Exclusive
    # Map shift -> list of crane_ids assigned
    assigned_cranes: Dict[int, List[str]] = field(default_factory=dict)


@dataclass
class Solution:
    """Complete solution for the BAP + QCAP problem."""

    vessel_solutions: List[VesselSolution]
    objective_value: float
    status: str  # "OPTIMAL", "FEASIBLE", "INFEASIBLE", etc.
