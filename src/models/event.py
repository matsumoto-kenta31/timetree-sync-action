from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar
from zoneinfo import ZoneInfo

# Google Calendar event colors (colorId -> RGB of the palette color).
GOOGLE_EVENT_COLORS: dict[str, tuple[int, int, int]] = {
    "1": (164, 189, 252),  # #a4bdfc lavender
    "2": (122, 231, 191),  # #7ae7bf sage
    "3": (219, 173, 255),  # #dbadff grape
    "4": (255, 136, 124),  # #ff887c flamingo
    "5": (251, 215, 91),  # #fbd75b banana
    "6": (255, 184, 120),  # #ffb878 tangerine
    "7": (70, 214, 219),  # #46d6db peacock
    "8": (225, 225, 225),  # #e1e1e1 graphite
    "9": (84, 132, 237),  # #5484ed blueberry
    "10": (81, 183, 73),  # #51b749 basil
    "11": (220, 33, 39),  # #dc2127 tomato
}


def nearest_google_color_id(color) -> str | None:
    """Map a TimeTree label color to the nearest Google Calendar colorId."""
    if color is None:
        return None
    if isinstance(color, int):
        color = f"#{color:06x}"
    if not isinstance(color, str):
        return None
    value = color.strip().lstrip("#")
    if len(value) == 8:  # RRGGBBAA -> drop alpha
        value = value[:6]
    if len(value) != 6:
        return None
    try:
        r, g, b = (int(value[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None

    def distance(rgb: tuple[int, int, int]) -> int:
        # Weighted RGB distance (redmean approximation inputs, simplified).
        return (
            3 * (r - rgb[0]) ** 2
            + 4 * (g - rgb[1]) ** 2
            + 2 * (b - rgb[2]) ** 2
        )

    return min(GOOGLE_EVENT_COLORS, key=lambda cid: distance(GOOGLE_EVENT_COLORS[cid]))


def extract_label_id(event: dict):
    """Extract label_id from a raw TimeTree event, trying multiple formats."""
    label_id = event.get("label_id")
    if label_id is not None:
        return label_id
    try:
        rel_id = event["relationships"]["label"]["data"]["id"]
        # Format may be "calendar_id,label_number" — take the label number.
        if isinstance(rel_id, str) and "," in rel_id:
            return int(rel_id.split(",")[-1])
        return int(rel_id)
    except (KeyError, TypeError, ValueError):
        return None


@dataclass
class Event:
    SYNC_SOURCE: ClassVar[str] = "timetree-sync-action"

    id: str
    title: str
    start: datetime
    end: datetime
    all_day: bool
    location: str | None = None
    description: str | None = None
    color_id: str | None = None

    @classmethod
    def from_timetree(cls, event: dict, label_colors: dict | None = None):
        start_tz = ZoneInfo(event["start_timezone"])
        end_tz = ZoneInfo(event["end_timezone"])

        color_id = None
        if label_colors:
            label_id = extract_label_id(event)
            if label_id is not None:
                color_id = nearest_google_color_id(label_colors.get(str(label_id)))

        return cls(
            id=event["id"],
            title=event["title"],
            start=datetime.fromtimestamp(
                event["start_at"] / 1000,
                tz=start_tz,
            ),
            end=datetime.fromtimestamp(
                event["end_at"] / 1000,
                tz=end_tz,
            ),
            all_day=event["all_day"],
            location=event.get("location") or None,
            description=event.get("note") or None,
            color_id=color_id,
        )

    def to_google(self, calendar_code: str) -> dict:
        event = {
            "summary": self.title,
            "extendedProperties": {
                "private": {
                    "sync_source": self.SYNC_SOURCE,
                    "timetree_calendar_code": calendar_code,
                    "timetree_id": self.id,
                }
            },
        }

        if self.all_day:
            event["start"] = {
                "date": self.start.strftime("%Y-%m-%d"),
            }
            event["end"] = {
                "date": self.end.strftime("%Y-%m-%d"),
            }
        else:
            event["start"] = {
                "dateTime": self.start.isoformat(),
                "timeZone": "Asia/Tokyo",
            }
            event["end"] = {
                "dateTime": self.end.isoformat(),
                "timeZone": "Asia/Tokyo",
            }

        if self.location:
            event["location"] = self.location

        if self.description:
            event["description"] = self.description

        if self.color_id:
            event["colorId"] = self.color_id

        return event

    def equals_google(self, google_event: dict, calendar_code: str) -> bool:
        google = self.to_google(calendar_code)

        return (
            google.get("summary") == google_event.get("summary")
            and google.get("location") == google_event.get("location")
            and google.get("description") == google_event.get("description")
            and google.get("start") == google_event.get("start")
            and google.get("end") == google_event.get("end")
            and google.get("colorId") == google_event.get("colorId")
        )
