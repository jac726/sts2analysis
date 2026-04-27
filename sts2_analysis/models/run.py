"""
Data model for a single STS2 run.
Field names are derived directly from the .run JSON schema (schema_version 8).
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone


@dataclass
class CardEntry:
    id: str
    floor_added_to_deck: int = 0
    upgraded: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "CardEntry":
        return cls(
            id=d.get("id", ""),
            floor_added_to_deck=d.get("floor_added_to_deck", 0),
            upgraded=d.get("upgraded", False),
        )


@dataclass
class RelicEntry:
    id: str
    floor_added_to_deck: int = 0

    @classmethod
    def from_dict(cls, d: dict) -> "RelicEntry":
        return cls(id=d.get("id", ""), floor_added_to_deck=d.get("floor_added_to_deck", 0))


@dataclass
class CardChoice:
    card_id: str
    was_picked: bool
    floor: int = 0

    @classmethod
    def from_dict(cls, d: dict, floor: int = 0) -> "CardChoice":
        return cls(
            card_id=(d.get("card") or {}).get("id", ""),
            was_picked=d.get("was_picked", False),
            floor=floor,
        )


@dataclass
class FloorStats:
    floor: int
    act: int
    map_point_type: str
    current_hp: int = 0
    max_hp: int = 0
    current_gold: int = 0
    damage_taken: int = 0
    gold_gained: int = 0
    gold_lost: int = 0
    gold_spent: int = 0
    hp_healed: int = 0
    max_hp_gained: int = 0
    max_hp_lost: int = 0
    card_choices: list[CardChoice] = field(default_factory=list)
    cards_gained: list[str] = field(default_factory=list)
    encounter_id: Optional[str] = None
    turns_taken: Optional[int] = None

    @classmethod
    def from_dict(cls, d: dict, floor: int, act: int) -> "FloorStats":
        player_stats = (d.get("player_stats") or [{}])
        ps = player_stats[0] if player_stats else {}
        rooms = d.get("rooms", [])
        encounter_id = None
        turns_taken = None
        if rooms:
            encounter_id = rooms[0].get("model_id") or rooms[0].get("encounter_id")
            turns_taken = rooms[0].get("turns_taken")
        return cls(
            floor=floor,
            act=act,
            map_point_type=d.get("map_point_type", ""),
            current_hp=ps.get("current_hp", 0),
            max_hp=ps.get("max_hp", 0),
            current_gold=ps.get("current_gold", 0),
            damage_taken=ps.get("damage_taken", 0),
            gold_gained=ps.get("gold_gained", 0),
            gold_lost=ps.get("gold_lost", 0),
            gold_spent=ps.get("gold_spent", 0),
            hp_healed=ps.get("hp_healed", 0),
            max_hp_gained=ps.get("max_hp_gained", 0),
            max_hp_lost=ps.get("max_hp_lost", 0),
            card_choices=[CardChoice.from_dict(c, floor) for c in ps.get("card_choices", [])],
            cards_gained=[c.get("id", "") for c in ps.get("cards_gained", [])],
            encounter_id=encounter_id,
            turns_taken=turns_taken,
        )


@dataclass
class Run:
    # Top-level fields
    win: bool = False
    was_abandoned: bool = False
    ascension: int = 0
    game_mode: str = "standard"
    seed: str = ""
    build_id: str = ""
    run_time: int = 0         # seconds
    start_time: int = 0       # unix epoch
    schema_version: int = 0
    acts: list[str] = field(default_factory=list)
    modifiers: list[str] = field(default_factory=list)
    killed_by_encounter: str = ""
    killed_by_event: str = ""

    # Player fields (from players[0])
    character: str = ""
    deck: list[CardEntry] = field(default_factory=list)
    relics: list[RelicEntry] = field(default_factory=list)
    potions: list[str] = field(default_factory=list)

    # Per-floor timeline
    floor_history: list[FloorStats] = field(default_factory=list)

    source_file: str = ""
    raw: dict = field(default_factory=dict)

    @property
    def datetime(self) -> Optional[datetime]:
        if self.start_time:
            return datetime.fromtimestamp(self.start_time, tz=timezone.utc)
        return None

    @property
    def run_time_minutes(self) -> float:
        return self.run_time / 60

    @property
    def floors_reached(self) -> int:
        return len(self.floor_history)

    @property
    def final_deck_ids(self) -> list[str]:
        return [c.id for c in self.deck]

    @property
    def relic_ids(self) -> list[str]:
        return [r.id for r in self.relics]

    @property
    def all_card_choices(self) -> list[CardChoice]:
        choices = []
        for floor in self.floor_history:
            choices.extend(floor.card_choices)
        return choices

    @classmethod
    def from_dict(cls, data: dict, *, keep_raw: bool = False) -> "Run":
        players = (data.get("players") or [{}])
        player = players[0] if players else {}

        # Safely get map_point_history to fix both CRASH-5 and PERF-1
        mph = (data.get("map_point_history") or [])

        floor_history = []
        prefix = 0
        for act_idx, act_floors in enumerate(mph):
            if not act_floors:  # Handle null/empty acts
                continue
            for floor_idx, floor_data in enumerate(act_floors):
                global_floor = prefix + floor_idx + 1
                floor_history.append(FloorStats.from_dict(floor_data, global_floor, act_idx + 1))
            prefix += len(act_floors)

        return cls(
            win=data.get("win", False),
            was_abandoned=data.get("was_abandoned", False),
            ascension=data.get("ascension", 0),
            game_mode=data.get("game_mode", "standard"),
            seed=data.get("seed", ""),
            build_id=data.get("build_id", ""),
            run_time=data.get("run_time", 0),
            start_time=data.get("start_time", 0),
            schema_version=data.get("schema_version", 0),
            acts=(data.get("acts") or []),
            modifiers=(data.get("modifiers") or []),
            killed_by_encounter=data.get("killed_by_encounter", ""),
            killed_by_event=data.get("killed_by_event", ""),
            character=player.get("character", ""),
            deck=[CardEntry.from_dict(c) for c in (player.get("deck") or [])],
            relics=[RelicEntry.from_dict(r) for r in (player.get("relics") or [])],
            potions=[p.get("id", "") for p in (player.get("potions") or [])],
            floor_history=floor_history,
            source_file=data.get("_source_file", ""),
            raw=data if keep_raw else {},
        )
