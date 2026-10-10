from copy import deepcopy

import pytest


@pytest.fixture
def frame():
    return deepcopy({
        "schemaVersion": 1, "roverId": "rover-1", "sequence": 42,
        "capturedAt": "2026-10-10T12:00:00.000Z",
        "roverPosition": {"frameId": "LOCAL_ENU_V1", "xM": 2.5, "yM": 1.2, "zM": 0},
        "positionUncertaintyRadiusM": 0.3,
        "link": {"status": "connected", "packetsSent": 42, "packetsLost": 2},
        "hazards": [{"id": "hazard-1", "type": "rock",
                     "position": {"frameId": "LOCAL_ENU_V1", "xM": 3.1, "yM": 2, "zM": 0},
                     "confidence": 0.87, "uncertaintyRadiusM": 0.4,
                     "observedAt": "2026-10-10T11:59:59.900Z"}],
    })
