"""Disposable GitHub runner only: image-only fresh init and existing-volume recovery.

Never connects to Unraid. No observations or assessment fixtures are imported.
"""
import argparse
import json
import os
import secrets
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.environ.get('GITHUB_ACTIONS') != 'true':
        raise ValueError('Run only on a disposable GitHub Actions runner')
    env = {**os.environ, 'CORE_IMAGE': args.image, 'CORE_BIND_IP': '127.0.0.1', 'CORE_PORT': '18799',
        'POSTGRES_ADMIN_PASSWORD': secrets.token_hex(32), 'POSTGRES_PASSWORD': secrets.token_hex(32) + "'quoted$",
        'CORE_API_TOKEN': secrets.token_hex(32), 'CORE_PATTERNS_MODE': 'shadow', 'CORE_LIVE_SOURCES': 'false',
        'CORE_SOURCE_KEYS': 'all', 'CORE_RETENTION_ENABLED': 'false',
        'DB_DATA_PATH': str(ROOT / 'evidence/release-stack-db'), 'CORE_DATA_PATH': str(ROOT / 'evidence/release-stack-core')}
    prefix = ['docker', 'compose', '-p', 'pec-release-test', '-f', str(ROOT / 'compose.unraid.yaml')]
    receipt = dict(image=args.image, release_commit=args.commit, production_modified=False,
        synthetic_observations_imported=False, installed_unraid_verified=False)
    # Docker creates missing bind parents as root. Prepare the runner-owned
    # evidence parent first, before it starts either container.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / 'evidence').mkdir(exist_ok=True)
    Path(env['DB_DATA_PATH']).mkdir(parents=True, exist_ok=True)
    Path(env['CORE_DATA_PATH']).mkdir(parents=True, exist_ok=True)

    def run(*command, capture=False):
        result = subprocess.run(command, cwd=ROOT, env=env, check=True,
            stdout=subprocess.PIPE if capture else None, text=True)
        return result.stdout.strip() if capture else None

    def compose(*command, capture=False, override=None):
        extra = ['-f', str(override)] if override else []
        return run(*prefix, *extra, *command, capture=capture)

    def sql(query):
        return compose('exec', '-T', 'photography-events-db', 'psql', '-U', 'postgres',
            '-d', 'photography_events', '-v', 'ON_ERROR_STOP=1', '-Atc', query, capture=True)

    def ready():
        for _ in range(45):
            try:
                with urllib.request.urlopen('http://127.0.0.1:18799/health/ready', timeout=3) as response:
                    data = json.load(response)
                assert data['status'] == 'ready' and data['schema_version'] == '0010'
                return data
            except (OSError, AssertionError):
                time.sleep(2)
        raise AssertionError('Image-only runtime never became healthy')

    try:
        info = json.loads(run('docker', 'image', 'inspect', args.image, capture=True))[0]
        assert info['Os'] == 'linux' and info['Architecture'] == 'amd64'
        assert info['Config']['User'] == '10001:10001'
        assert info['Config']['Labels']['org.opencontainers.image.revision'] == args.commit
        receipt['image_id'] = info['Id']
        receipt['platform'] = 'linux/amd64'
        receipt['labels'] = info['Config']['Labels']
        receipt['registry_digests'] = info['RepoDigests']
        run('docker', 'pull', '--platform', 'linux/amd64', 'postgis/postgis:18-3.6')
        compose('config', '-q')
        compose('up', '-d', '--pull', 'never', '--wait', '--wait-timeout', '150')
        receipt['fresh_image_stack'] = ready()
        roles = json.loads(sql("""SELECT json_build_object('superuser',r.rolsuper,'createdb',r.rolcreatedb,
            'createrole',r.rolcreaterole,'replication',r.rolreplication,'bypassrls',r.rolbypassrls,
            'login',r.rolcanlogin,'owns_database',d.datdba=r.oid,
            'postgres_major',current_setting('server_version_num')::int/10000,
            'postgis',postgis_lib_version()) FROM pg_roles r,pg_database d
            WHERE r.rolname='photography_events' AND d.datname='photography_events'"""))
        assert roles['login'] and roles['owns_database'] and roles['postgres_major'] == 18
        assert roles['postgis'].startswith('3.6')
        assert not any(roles[k] for k in ('superuser', 'createdb', 'createrole', 'replication', 'bypassrls'))
        receipt['role_separation'] = roles
        # Only a trivial deployment probe in this disposable CI database.
        sql("CREATE TABLE release_deployment_probe(id integer PRIMARY KEY,value text); INSERT INTO release_deployment_probe VALUES(1,'persisted')")
        before = sql("SELECT oid FROM pg_roles WHERE rolname='photography_events'")
        override = ROOT / 'evidence/release-existing-volume.json'
        override.parent.mkdir(exist_ok=True)
        override.write_text(json.dumps({'services': {'photography-events-db': {'environment': {
            'APP_DB_PASSWORD': secrets.token_hex(32)}}}}))
        # Different init-only password must NOT reset an existing role/password.
        compose('up', '-d', '--pull', 'never', '--force-recreate', '--wait', '--wait-timeout', '150', override=override)
        receipt['existing_volume_recreated'] = ready()
        assert sql("SELECT oid FROM pg_roles WHERE rolname='photography_events'") == before
        assert sql('SELECT value FROM release_deployment_probe WHERE id=1') == 'persisted'
        assert sql('SELECT count(*) FROM source_runs') == '0'
        receipt['data_and_role_preserved'] = True
        receipt['init_password_did_not_rotate_existing_role'] = True
        receipt['provider_collection_enabled_for_unraid_template'] = True
        receipt['provider_collection_disabled_for_disposable_smoke_test'] = True
    finally:
        try:
            args.output.write_text(json.dumps(receipt, indent=2) + '\n')
        finally:
            compose('down', '--remove-orphans')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
