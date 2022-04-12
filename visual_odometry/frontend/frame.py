from dataclasses import dataclass, field
from typing import List, OrderedDict
import numpy as np


@dataclass
class Frame:
    id: int
    image: np.ndarray
    key_pts: np.ndarray = np.array([])
    desc: np.ndarray = np.empty(shape=())
    undist: np.ndarray = np.empty(shape=())
    pose: np.ndarray = np.empty(shape=())
    observations: OrderedDict = field(default_factory=lambda: OrderedDict([]))
    is_keyframe: bool = False


def create_frame(id, image):
    return Frame(id, image)