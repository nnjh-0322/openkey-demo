"""기록기: SCHEMA.md v1 형식의 JSONL. 영상·사진·음성은 받지도 쓰지도 않는다."""
from __future__ import annotations

import datetime
import json
import pathlib
import random


def iso(dt: datetime.datetime) -> str:
    return dt.isoformat(timespec="milliseconds")


def new_attempt_id(wall: datetime.datetime, rng: random.Random | None = None) -> str:
    r = rng or random
    return f"{wall:%Y%m%d-%H%M%S}-{r.randrange(16 ** 4):04x}"


class Recorder:
    def __init__(self, attempt_id: str, t0: float, wall0: datetime.datetime, path: pathlib.Path | None = None, keep=20000):
        self.attempt, self.t0, self.wall0, self.path = attempt_id, t0, wall0, path
        self.seq = 0
        self.records = []
        self.keep = keep
        self._fh = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(path, "a", encoding="utf-8", newline="\n")

    def ms(self, now: float) -> int:
        return int(round((now - self.t0) * 1000))

    def wall(self, now: float) -> datetime.datetime:
        return self.wall0 + datetime.timedelta(seconds=now - self.t0)

    def write(self, kind: str, now: float, **fields) -> dict:
        self.seq += 1
        rec = {"v": 1, "attempt": self.attempt, "seq": self.seq, "t": iso(self.wall(now)), "ms": self.ms(now), "kind": kind}
        rec.update(fields)
        self.records.append(rec)
        if len(self.records) > self.keep:
            del self.records[: len(self.records) - self.keep]
        if self._fh:
            self._fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._fh.flush()
        return rec

    def after(self, seq: int) -> list:
        return [r for r in self.records if r["seq"] > seq]

    def close(self):
        if self._fh:
            self._fh.close()
            self._fh = None
