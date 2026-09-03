from dataclasses import dataclass
from typing import Union


CameraInput = Union[int, str]


@dataclass
class CameraSource:
    """
    Represents a video source.

    source can be:
        int  -> local webcam/USB camera index
        str  -> RTSP/IP camera URL
    """

    camera_id: str
    name: str
    source: CameraInput
    location: str = ""
    enabled: bool = True

    @property
    def is_network_camera(self) -> bool:
        """Return True when this is an RTSP/network camera."""
        return isinstance(self.source, str)

    def __str__(self) -> str:
        return (
            f"{self.camera_id} | "
            f"{self.name} | "
            f"{self.location}"
        )