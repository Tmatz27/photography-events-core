"""Fail-closed release policy; development pushes never publish images."""
import json
import os
import re
import subprocess
from pathlib import Path

IMAGE = 'ghcr.io/tmatz27/photography-events-core'
VERSION = re.compile(r'v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*))?\Z')


def metadata(event, sha, *, actual_commit, tag_commit):
    release = event.get('release', {})
    tag = release.get('tag_name', '')
    match = VERSION.fullmatch(tag)
    if (event.get('action') != 'published' or release.get('draft') is not False
            or not match or len(tag) > 100 or type(release.get('prerelease')) is not bool):
        raise ValueError('Only a published, versioned release can publish an image')
    if bool(match.group(4)) != release['prerelease']:
        raise ValueError('Release prerelease flag must match version suffix')
    if not re.fullmatch('[0-9a-f]{40}', sha) or actual_commit != sha or tag_commit != sha:
        raise ValueError('Release, tag and checked-out commit must agree')
    channel = 'preview' if release['prerelease'] else 'latest'
    return dict(commit=sha, version=tag, channel=channel, image=IMAGE,
        version_image=f'{IMAGE}:{tag}', sha_image=f'{IMAGE}:sha-{sha}', channel_image=f'{IMAGE}:{channel}')


def main():
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    sha = os.environ['GITHUB_SHA']
    tag = event['release']['tag_name']
    actual = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
    # Resolve tag without interpolating provider/release text into a shell.
    tagged = subprocess.check_output(['git', 'rev-parse', f'refs/tags/{tag}^{{commit}}'], text=True).strip()
    result = metadata(event, sha, actual_commit=actual, tag_commit=tagged)
    with Path(os.environ['GITHUB_OUTPUT']).open('a') as output:
        for key, value in result.items():
            output.write(f'{key}={value}\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
