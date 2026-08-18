#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["chess"]
# ///

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import quote

import chess
import chess.svg

ROOT: Final = Path(__file__).resolve().parent
GAME_PATH: Final = ROOT / "data" / "game.json"
README_PATH: Final = ROOT / "README.md"
BOARD_PATH: Final = ROOT / "board.svg"
BOARD_PX: Final = 520
MOVE_RE: Final = re.compile(
    r"^chess:\s*move\s+([a-h][1-8])\s+to\s+([a-h][1-8])\s*$", re.IGNORECASE
)
NEW_RE: Final = re.compile(r"^chess:\s*start new game\s*$", re.IGNORECASE)
MARKERS: Final = (
    ("board", "<!-- BEGIN CHESS BOARD -->", "<!-- END CHESS BOARD -->", False),
    ("moves", "<!-- BEGIN MOVES LIST -->", "<!-- END MOVES LIST -->", False),
    ("turn", "<!-- BEGIN TURN -->", "<!-- END TURN -->", True),
)


@dataclass(frozen=True, slots=True)
class Game:
    fen: str
    history: tuple[tuple[str, str, str], ...]
    scores: tuple[tuple[str, int], ...]
    finished: bool


@dataclass(frozen=True, slots=True)
class Result:
    ok: bool
    comment: str
    game: Game | None


def main() -> None:
    result_path = Path("/tmp/chess-result.json")
    try:
        payload = _run()
    except Exception as exc:  # noqa: BROAD_EXCEPT_OK
        payload = {"ok": False, "comment": f"bot error: {exc}"}
    text = json.dumps(payload)
    result_path.write_text(text + "\n", encoding="utf-8")
    print(text, flush=True)


def _run() -> dict[str, bool | str]:
    if len(sys.argv) < 2:
        raise SystemExit("usage: play.py play|seed ...")
    cmd = sys.argv[1]
    if cmd == "seed":
        _, _, owner, repo = sys.argv
        result = apply("Chess: Start new game", owner, owner, repo)
    elif cmd == "play":
        _, _, title, author, owner, repo = sys.argv
        result = apply(title, author, owner, repo)
    else:
        raise SystemExit(f"unknown command: {cmd}")
    if result.game is not None:
        save(result.game)
        README_PATH.write_text(
            render(README_PATH.read_text(encoding="utf-8"), result.game, repo),
            encoding="utf-8",
        )
    return {"ok": result.ok, "comment": result.comment}


def apply(title: str, author: str, owner: str, repo: str) -> Result:
    del repo
    game = load()
    if NEW_RE.fullmatch(title.strip()):
        if game is not None and not game.finished and author != owner:
            return Result(False, f"@{author}: a game is already in progress.", None)
        scores = game.scores if game is not None else ()
        return Result(
            True,
            f"@{author}: new game started. White moves first.",
            Game(chess.Board().fen(), (("start", author, ""),), scores, False),
        )
    move_match = MOVE_RE.fullmatch(title.strip())
    if move_match is None:
        return Result(False, f"@{author}: I only understand `Chess: Move E2 to E4`.", None)
    if game is None:
        return Result(False, f"@{author}: no game in progress. Open `Chess: Start new game`.", None)
    if game.finished:
        return Result(False, f"@{author}: this game is over. Open `Chess: Start new game`.", None)
    if game.history and game.history[0][0] == "move" and game.history[0][1] == author:
        return Result(False, f"@{author}: you moved last turn. Wait for someone else.", None)
    source, dest = move_match.group(1).lower(), move_match.group(2).lower()
    board = chess.Board(game.fen)
    move = _legal(board, source, dest)
    if move is None:
        return Result(False, f"@{author}: `{source.upper()} to {dest.upper()}` is not a legal move.", None)
    board.push(move)
    pretty = f"{source.upper()} to {dest.upper()}"
    comment = f"@{author}: `{pretty}` played. Refresh the profile in about 30 seconds!"
    if board.is_checkmate():
        comment = f"@{author}: `{pretty}` — checkmate {board.result()}"
    elif board.is_stalemate():
        comment = f"@{author}: `{pretty}` — stalemate"
    elif board.is_check():
        comment = f"@{author}: `{pretty}` — check"
    return Result(True, comment, _after_move(game, board, author, move.uci()))


def load() -> Game | None:
    if not GAME_PATH.exists():
        return None
    raw = json.loads(GAME_PATH.read_text(encoding="utf-8"))
    history = tuple((str(k), str(a), str(u)) for k, a, u in raw["history"])
    scores = tuple((str(user), int(n)) for user, n in raw["scores"])
    return Game(str(raw["fen"]), history, scores, bool(raw["finished"]))


def save(game: Game) -> None:
    GAME_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "fen": game.fen,
        "history": [list(item) for item in game.history],
        "scores": [list(item) for item in game.scores],
        "finished": game.finished,
    }
    GAME_PATH.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def render(readme: str, game: Game, repo: str) -> str:
    board = chess.Board(game.fen)
    sections = {
        "board": _board(board, game.history),
        "moves": _moves(board, repo),
        "turn": "game over" if board.is_game_over() else ("white" if board.turn else "black"),
    }
    text = readme
    for key, begin, end, inline in MARKERS:
        start, stop = text.find(begin), text.find(end)
        if start == -1 or stop == -1 or stop < start:
            continue
        body = sections[key].rstrip() if inline else f"\n{sections[key].rstrip()}\n"
        text = text[: start + len(begin)] + body + text[stop:]
    return text


def _legal(board: chess.Board, source: str, dest: str) -> chess.Move | None:
    promoted = chess.Move.from_uci(f"{source}{dest}q")
    if promoted in board.legal_moves:
        return promoted
    plain = chess.Move.from_uci(f"{source}{dest}")
    if plain in board.legal_moves:
        return plain
    return None


def _after_move(game: Game, board: chess.Board, author: str, uci: str) -> Game:
    scores = {user: n for user, n in game.scores}
    scores[author] = scores.get(author, 0) + 1
    return Game(
        board.fen(),
        (("move", author, uci), *game.history),
        tuple(scores.items()),
        board.is_game_over(),
    )


def _board(board: chess.Board, history: tuple[tuple[str, str, str], ...]) -> str:
    lastmove = None
    if history and history[0][0] == "move":
        lastmove = chess.Move.from_uci(history[0][2])
    BOARD_PATH.write_text(
        chess.svg.board(
            board,
            size=BOARD_PX,
            lastmove=lastmove,
            coordinates=True,
            orientation=board.turn,
        ),
        encoding="utf-8",
    )
    return f'<img src="board.svg" width="{BOARD_PX}" alt="chess board" />'


def _moves(board: chess.Board, repo: str) -> str:
    if board.is_game_over():
        return f"**Game over** (`{board.result()}`). [Start a new game]({_link(repo, 'Chess: Start new game')}).\n"
    grouped: dict[str, set[str]] = {}
    for move in board.legal_moves:
        grouped.setdefault(chess.square_name(move.from_square).upper(), set()).add(
            chess.square_name(move.to_square).upper()
        )
    lines = ["**Check!** Choose carefully.\n"] if board.is_check() else []
    lines += ["| FROM | TO |", "| :---: | :--- |"]
    for source in sorted(grouped):
        dests = ", ".join(f"[{d}]({_link(repo, f'Chess: Move {source} to {d}')})" for d in sorted(grouped[source]))
        lines.append(f"| **{source}** | {dests} |")
    return "\n".join(lines) + "\n"


def _link(repo: str, title: str) -> str:
    body = quote("Just click Submit new issue!! Do not change the title.")
    return f"https://github.com/{repo}/issues/new?title={quote(title)}&body={body}"


if __name__ == "__main__":
    main()
