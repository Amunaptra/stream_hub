from __future__ import annotations

import json

import pytest

from stream_agent.models import PlaylistConfig, StreamItem
from stream_agent.settings import Settings
from stream_agent.storage import DeviceStore, RevisionConflict


def make_store(tmp_path) -> DeviceStore:
    return DeviceStore(Settings(data_dir=tmp_path / "data", runtime_dir=tmp_path / "run"))


def test_identity_is_persistent_and_has_unique_token(tmp_path) -> None:
    store = make_store(tmp_path)

    first = store.load_or_create_identity()
    second = store.load_or_create_identity()

    assert first == second
    assert len(first.token) >= 32
    assert first.device_id


def test_playlist_is_written_atomically_and_backed_up(tmp_path) -> None:
    store = make_store(tmp_path)
    assert store.load_playlist().revision == 0

    revision_one = PlaylistConfig(
        revision=1,
        streams=[StreamItem(id="salon", url="http://media/salon.m3u8")],
    )
    applied, changed = store.apply_playlist(revision_one)

    assert changed is True
    assert applied.revision == 1
    assert store.load_playlist() == revision_one
    backup = json.loads((store.settings.data_dir / "playlist.json.bak").read_text())
    assert backup["revision"] == 0


def test_same_revision_is_idempotent_but_cannot_change_content(tmp_path) -> None:
    store = make_store(tmp_path)
    initial = store.load_playlist()

    _, changed = store.apply_playlist(initial)
    assert changed is False

    conflicting = PlaylistConfig(
        revision=0,
        streams=[StreamItem(id="new", url="https://media/new.m3u8")],
    )
    with pytest.raises(RevisionConflict, match="different content"):
        store.apply_playlist(conflicting)


def test_older_revision_is_rejected(tmp_path) -> None:
    store = make_store(tmp_path)
    store.load_playlist()
    store.apply_playlist(PlaylistConfig(revision=2))

    with pytest.raises(RevisionConflict, match="older"):
        store.apply_playlist(PlaylistConfig(revision=1))


def test_backup_can_be_restored(tmp_path) -> None:
    store = make_store(tmp_path)
    store.load_playlist()
    store.apply_playlist(PlaylistConfig(revision=1))

    restored = store.restore_playlist_backup()

    assert restored.revision == 0
    assert store.load_playlist().revision == 0


def test_command_results_are_persistent_and_idempotent(tmp_path) -> None:
    store = make_store(tmp_path)

    store.save_command_result("command-1", True, "reboot requested")
    reloaded = make_store(tmp_path)

    assert reloaded.command_result("command-1") == (True, "reboot requested")
    assert reloaded.command_result("missing") is None
