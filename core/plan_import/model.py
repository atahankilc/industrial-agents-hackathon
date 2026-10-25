"""Types shared by the plan-import stages. Pixel coordinates are image coordinates (x right, y down)."""

from dataclasses import dataclass, field

import numpy as np

Point = tuple[float, float]


@dataclass
class Source:
    id: str  # "s1", "s2", … in upload order
    origin: str  # "plan.pdf p2", "IMG_1.jpeg"
    image: np.ndarray  # BGR uint8, long side ≤ PROCESS_MAX_SIDE
    text: str = ""  # PDF page text, "" for images


@dataclass
class Cell:
    id: int  # 1.. in reading order (top-left first)
    polygon: list[Point]  # px, not closed
    area_px: float
    outside: bool  # the exterior region (touches the image border)


@dataclass
class DoorCandidate:
    cells: tuple  # (a, b) with a < b, or (a, "outside")
    position: Point  # px
    width_px: float


@dataclass
class Segmentation:
    method: str  # "walls" | "colours" | "coarse"
    cells: dict[int, Cell]
    adjacency: dict[tuple[int, int], list[Point]]  # sorted pair → shared boundary points (px)
    doors: list[DoorCandidate]


@dataclass
class CellLabel:
    type: str  # room | corridor | stair | lift | hall | outdoor
    room_type: str  # dataset list (docs/kit/data-format.md#room-types)
    name: str
    ref: str = ""


@dataclass
class FloorPlan:
    level: int
    name: str
    source_id: str
    image: np.ndarray  # rectified + cropped, BGR
    seg: Segmentation
    labels: dict[int, CellLabel] = field(default_factory=dict)  # by surviving cell id
    doors: list[DoorCandidate] = field(default_factory=list)  # accepted doors / entrances
    m_per_px: float | None = None
    scale_method: str | None = None
    transform: np.ndarray | None = None  # 2x3: px → frame metres (y up), set by stack.align
    alignment: str | None = None
    low_confidence: bool = False
