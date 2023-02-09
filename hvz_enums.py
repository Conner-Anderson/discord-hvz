from enum import Enum, auto, unique

@unique
class GameRole(Enum):
    PLAYER = 1
    HUMAN = 2
    ZOMBIE = 3

@unique
class GameChannel(Enum):
    TAG_ANNOUNCEMENT = 1
    TAG_REPORT = 2
    ZOMBIE = 3

