#!/usr/bin/env python3
"""Enumerate recordings on a DTCP-IP recorder (nasne) without credentials.

Uses pydtcpip's DLNA stack (SSDP discovery + ContentDirectory Browse) and
prints a JSON listing: title, ID, resources (res URL / protocolInfo / size),
and protection info (remaining copy count from av:COGCount, Move support).

Run with pydtcpip's venv Python so that `pydtcpip` is importable:
    <pydtcpip>/.venv/bin/python list_recordings.py
"""

import argparse
import asyncio
import json
import sys

from pydtcpip.dlna.client import DLNAClient
from pydtcpip.models import Container, Recording


def content_id_of(object_id: str) -> str:
    """Extract the stable content ID (`pvr?id=` value) from a DIDL object ID.

    The same recording appears under several containers (all / genre / date)
    with different object IDs; the `pvr?id=` part identifies the recording.
    """
    marker = 'pvr?id='
    if marker in object_id:
        return object_id.split(marker, 1)[1]
    return object_id


async def collect_recordings(server) -> list[Recording]:
    """Recursively browse from the root container and collect recordings."""
    seen_containers: set[str] = set()
    recordings: dict[str, Recording] = {}

    async def walk(object_id: str, depth: int) -> None:
        if object_id in seen_containers or depth > 8:
            return
        seen_containers.add(object_id)
        for item in await server.browse_all(object_id):
            if isinstance(item, Recording):
                # Live tuner channels are listed as videoBroadcast items;
                # they are not recordings (same distinction as pydtcpip's CLI).
                if item.upnp_class.startswith('object.item.videoItem.videoBroadcast'):
                    continue
                key = content_id_of(item.id)
                existing = recordings.get(key)
                # Prefer the canonical flat-list entry (0/video/all/...)
                if existing is None or (
                    item.id.startswith('0/video/all/') and not existing.id.startswith('0/video/all/')
                ):
                    recordings[key] = item
            elif isinstance(item, Container):
                await walk(item.id, depth + 1)

    await walk('0', 0)
    return list(recordings.values())


def protection_dump(value) -> dict:
    return {'status': value.status, 'value': value.value}


def recording_dump(recording: Recording) -> dict:
    original = recording.original_resource
    resources = []
    for resource in recording.resources:
        resources.append(
            {
                'url': resource.url,
                'protocol_info': resource.protocol_info.raw,
                'size': resource.size,
                'cleartext_size': resource.cleartext_size,
                'is_original': resource is original,
            }
        )
    return {
        'id': recording.id,
        'content_id': content_id_of(recording.id),
        'parent_id': recording.parent_id,
        'title': recording.title,
        'date': recording.date,
        'duration': recording.duration,
        'channel_name': recording.channel_name,
        'description': recording.description,
        'long_description': recording.long_description,
        'genres': list(recording.genres),
        'upnp_class': recording.upnp_class,
        'remaining_copy_count': protection_dump(recording.protection.remaining_copy_count),
        'is_move_supported': protection_dump(recording.protection.is_move_supported),
        'is_transaction_move_supported': protection_dump(
            recording.protection.is_transaction_move_supported
        ),
        'resources': resources,
    }


async def run(timeout: float) -> int:
    async with DLNAClient() as dlna:
        servers = await dlna.discover(timeout=timeout, port=57000)
        if not servers:
            print('no media servers found', file=sys.stderr)
            return 1
        server = next((s for s in servers if s.profile.name == 'sie_nasne'), None)
        if server is None:
            if len(servers) != 1:
                print('multiple servers found, none matched the sie_nasne profile', file=sys.stderr)
                return 1
            server = servers[0]
        recordings = await collect_recordings(server)
        result = {
            'server': {
                'friendly_name': server.description.friendly_name,
                'manufacturer': server.description.manufacturer,
                'model_name': server.description.model_name,
                'profile': server.profile.name,
                'location': server.description.location,
            },
            'recordings': [recording_dump(recording) for recording in recordings],
        }
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write('\n')
    return 0


def main() -> int:
    # The listing JSON carries Japanese titles; force UTF-8 on stdout so
    # non-UTF-8 consoles/pipes (e.g. Windows cp932) cannot corrupt it.
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    parser = argparse.ArgumentParser(description='List recordings on the nasne (no credentials).')
    parser.add_argument('--timeout', type=float, default=5.0, help='SSDP discovery timeout in seconds')
    args = parser.parse_args()
    return asyncio.run(run(args.timeout))


if __name__ == '__main__':
    sys.exit(main())
