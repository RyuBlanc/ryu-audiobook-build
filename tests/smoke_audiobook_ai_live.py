from __future__ import annotations

import os
from pathlib import Path
import tempfile
import sys
import traceback

from app.ai.brain import AudiobookBrain
from app.chapters.detector import Chapter


def main() -> None:
    endpoint = os.environ.get('RYU_AI_SERVER_URL')
    if not endpoint:
        raise SystemExit('RYU_AI_SERVER_URL is required for the live AI smoke test.')

    sample = (
        'Haruka looked at Rahul as rain struck the classroom windows. '
        '"We should go now," Haruka said quietly. '
        'Rahul stared at the dark corridor. "Wait for me," he replied. '
        'The room felt cold and tense, and neither of them wanted to speak about Kyoto.'
    )
    chapter = Chapter(1, 'AI Smoke Chapter', sample)

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


if __name__ == '__main__':
    try:
        print("LIVE_AUDIOBOOK_AI_PYTHON=", sys.executable, flush=True)
        main()
    except BaseException:
        traceback.print_exc()
        raise