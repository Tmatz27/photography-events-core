"""Release gate and image-only deployment boundaries; no engine behavior changes."""
import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_metadata', ROOT / 'tools/release_metadata.py')
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
SHA = 'a' * 40


def event(tag='v0.1.0-rc.1', prerelease=True, **changes):
    return dict(action='published', release=dict(tag_name=tag, prerelease=prerelease, draft=False, **changes))


@pytest.mark.parametrize('tag,pre,channel', [('v0.1.0-rc.1', True, 'preview'), ('v0.1.0', False, 'latest')])
def test_release_only_approved_stable_can_select_latest(tag, pre, channel):
    result = policy.metadata(event(tag, pre), SHA, actual_commit=SHA, tag_commit=SHA)
    assert result['channel'] == channel and result['commit'] == SHA
    assert result['sha_image'].endswith(':sha-' + SHA)
    assert result['version_image'].endswith(':' + tag)


@pytest.mark.parametrize('change', ['development', 'draft', 'bad_tag', 'prerelease_as_stable', 'moved_tag', 'wrong_checkout'])
def test_release_rejects_unapproved_or_mismatched_publication(change):
    value, actual, tagged = event(), SHA, SHA
    if change == 'development':
        value['action'] = 'push'
    elif change == 'draft':
        value['release']['draft'] = True
    elif change == 'bad_tag':
        value['release']['tag_name'] = 'v0.1.0\nlatest'
    elif change == 'prerelease_as_stable':
        value['release']['prerelease'] = False
    elif change == 'moved_tag':
        tagged = 'b' * 40
    else:
        actual = 'b' * 40
    with pytest.raises(ValueError):
        policy.metadata(value, SHA, actual_commit=actual, tag_commit=tagged)


def test_image_only_stack_preserves_paths_network_credentials_and_health():
    compose = yaml.safe_load((ROOT / 'compose.unraid.yaml').read_text())
    old = yaml.safe_load((ROOT / 'compose.yaml').read_text())
    assert compose['networks'] == old['networks']
    assert set(compose['services']) == set(old['services'])
    for key, service in compose['services'].items():
        before = old['services'][key]
        assert 'build' not in service and service['pull_policy'] == 'always'
        assert service['networks'] == before['networks'] and service['healthcheck'] == before['healthcheck']
        assert service['restart'] == before['restart']
        assert service['volumes'] == before['volumes'][:1]
    db = compose['services']['photography-events-db']
    core = compose['services']['photography-events-core']
    assert db['image'] == 'postgis/postgis:18-3.6' and db['environment'] == old['services']['photography-events-db']['environment']
    assert not db.get('ports') and core['ports'] == old['services']['photography-events-core']['ports']
    assert core['depends_on'] == old['services']['photography-events-core']['depends_on']
    assert 'POSTGRES_ADMIN_PASSWORD' not in core['environment'] and core['platform'] == 'linux/amd64'
    assert core['environment']['CORE_SOURCE_KEYS'].endswith(':-all}')
    assert core['environment']['CORE_PATTERNS_MODE'].endswith(':-shadow}')
    assert core['environment']['CORE_LIVE_SOURCES'].endswith(':-true}')
    for key in old['services']['photography-events-core']['environment']:
        assert key in core['environment']
    text = (ROOT / 'compose.unraid.yaml').read_text()
    assert '/repo' not in text and './scripts/' not in text
    assert 'exec /usr/local/bin/docker-entrypoint.sh "$$@"' in text
    assert 'NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS' in text
    assert "PASSWORD :'app_password'" in text


def test_release_workflow_cannot_publish_after_failed_validation_or_on_main_push():
    workflow = yaml.load((ROOT / '.github/workflows/release.yml').read_text(), Loader=yaml.BaseLoader)
    assert workflow['on'] == {'release': {'types': ['published']}}
    publish = workflow['jobs']['publish']
    assert publish['needs'] == ['release', 'validation'] and 'if' not in publish
    assert publish['permissions']['packages'] == 'write'
    assert workflow['jobs']['validation']['uses'] == './.github/workflows/validate.yml'
    steps = publish['steps']
    build = next(s for s in steps if 'build-push-action' in s.get('uses', ''))
    assert build['with']['target'] == 'runtime' and build['with']['platforms'] == 'linux/amd64'
    assert build['with']['push'] == 'false' and build['with']['load'] == 'true'
    smoke = next(i for i, s in enumerate(steps) if s.get('name', '').startswith('Verify image-only'))
    push = next(i for i, s in enumerate(steps) if s.get('name', '').startswith('Publish only'))
    assert smoke < push
    login = next(s for s in steps if 'login-action' in s.get('uses', ''))
    assert login['with']['password'] == '${{ secrets.GITHUB_TOKEN }}'
    verify = workflow['jobs']['verify-public']
    assert verify['needs'] == ['release', 'publish']
    anonymous = verify['steps'][1]['run']
    assert 'DOCKER_CONFIG=$(mktemp -d)' in anonymous and 'docker pull --platform linux/amd64' in anonymous
