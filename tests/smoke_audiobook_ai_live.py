from __future__ import annotations

import os
from pathlib import Path
import tempfile
import sys
import traceback
import time
import subprocess
import urllib.request
from urllib.parse import urlparse

from app.ai.brain import AudiobookBrain
from app.chapters.detector import Chapter


def _health(endpoint: str) -> bool:
    try:
        with urllib.request.urlopen(endpoint.rstrip('/') + '/health', timeout=2) as response:
            return int(getattr(response, 'status', 200)) == 200
    except Exception:
        return False


def _start_local_server(endpoint: str):
    """Start the CI's local llama server when the workflow has already cleaned it up.

    The normal application never uses this helper; it exists only to make the
    integration smoke deterministic across GitHub Actions Windows step
    boundaries. The workflow places the binary and model in RUNNER_TEMP.
    """
    parsed = urlparse(endpoint)
    if parsed.scheme not in {'http', 'https'} or not parsed.hostname or not parsed.port:
        raise RuntimeError(f'Invalid RYU_AI_SERVER_URL: {endpoint}')

    root = Path(os.environ.get('RUNNER_TEMP', tempfile.gettempdir())) / 'ryu-ai-smoke'
    binary = Path(os.environ.get('RYU_AI_SERVER_BINARY', ''))
    model = Path(os.environ.get('RYU_AI_MODEL', ''))
    if not binary:
        matches = list(root.rglob('llama-server.exe'))
        binary = matches[0] if matches else Path('llama-server.exe')
    if not model:
        model = root / 'Qwen3-0.6B-Q5_K_M.gguf'
    if not binary.is_file():
        raise RuntimeError(f'AI smoke server binary was not found: {binary}')
    if not model.is_file():
        raise RuntimeError(f'AI smoke model was not found: {model}')

    stdout_log = root / 'brain-smoke.stdout.log'
    stderr_log = root / 'brain-smoke.stderr.log'
    stdout_log.parent.mkdir(parents=True, exist_ok=True)
    stdout = stdout_log.open('a', encoding='utf-8', errors='replace')
    stderr = stderr_log.open('a', encoding='utf-8', errors='replace')
    command = [
        str(binary), '-m', str(model),
        '--host', parsed.hostname,
        '--port', str(parsed.port),
        '--ctx-size', '4096',
        '--threads', '4',
        '--no-webui',
        '--reasoning', 'off',
        '--reasoning-format', 'none',
    ]
    creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
    process = subprocess.Popen(
        command,
        stdout=stdout,
        stderr=stderr,
        creationflags=creationflags,
    )
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        if process.poll() is not None:
            stdout.close(); stderr.close()
            detail = stderr_log.read_text(encoding='utf-8', errors='replace')[-5000:]
            raise RuntimeError(f'AI smoke llama-server exited with code {process.returncode}: {detail}')
        if _health(endpoint):
            return process, stdout, stderr
        time.sleep(1)
    process.terminate()
    stdout.close(); stderr.close()
    raise RuntimeError('AI smoke llama-server did not become healthy within 90 seconds.')


def main() -> None:
    endpoint = os.environ.get('RYU_AI_SERVER_URL')
    if not endpoint:
        raise SystemExit('RYU_AI_SERVER_URL is required for the live AI smoke test.')

    server = None
    streams = ()
    if not _health(endpoint):
        server, *streams = _start_local_server(endpoint)

    sample = (
        'Haruka looked at Rahul as rain struck the classroom windows. '
        '"We should go now," Haruka said quietly. '
        'Rahul stared at the dark corridor. "Wait for me," he replied. '
        'The room felt cold and tense, and neither of them wanted to speak about Kyoto.'
    )
    chapter = Chapter(1, 'AI Smoke Chapter', sample)

    try:
        with tempfile.TemporaryDirectory(prefix='ryu-ai-brain-smoke-') as temp:
            brain = AudiobookBrain(Path(temp))
            try:
                result = brain.analyze_book([chapter])
            finally:
                brain.close()

        required = {'chapter', 'title', 'characters', 'dialogue', 'scenes', 'pronunciation', 'continuity_notes'}
        for key in required:
            if key not in result['chapters'][0]:
                raise SystemExit(f'Missing analysis key: {key}')

        chapter_result = result['chapters'][0]
        warnings = chapter_result.get('warnings', [])
        if warnings:
            raise SystemExit('Audiobook AI used a fallback/warning path: ' + ' | '.join(warnings))
        if not chapter_result.get('characters'):
            raise SystemExit('Audiobook AI returned no characters in the live smoke test.')
        if not chapter_result.get('dialogue'):
            raise SystemExit('Audiobook AI returned no dialogue in the live smoke test.')
        if not chapter_result.get('scenes'):
            raise SystemExit('Audiobook AI returned no scene analysis in the live smoke test.')

        print('LIVE_AUDIOBOOK_AI_BRAIN_SMOKE=PASS')
        print('characters=', len(chapter_result['characters']))
        print('dialogue=', len(chapter_result['dialogue']))
        print('scenes=', len(chapter_result['scenes']))
        print('pronunciation=', len(chapter_result['pronunciation']))
    finally:
        if server is not None:
            try:
                if server.poll() is None:
                    server.terminate()
                    server.wait(timeout=8)
            except Exception:
                try:
                    server.kill()
                except Exception:
                    pass
        for stream in streams:
            try:
                stream.close()
            except Exception:
                pass


if __name__ == '__main__':
    try:
        print('LIVE_AUDIOBOOK_AI_PYTHON=', sys.executable, flush=True)
        main()
    except BaseException:
        traceback.print_exc()
        raise
